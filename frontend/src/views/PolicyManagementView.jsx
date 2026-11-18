import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  Upload,
  Clock,
  CheckCircle,
  AlertCircle,
  FileText,
  ChevronDown,
  ChevronRight,
  ArrowRight,
  TrendingUp,
} from 'lucide-react';
import { fetchAllPolicies, fetchPolicyDetail, ingestPolicy, approvePolicy } from '../api';

export default function PolicyManagementView({ onPolicyActivated }) {
  const [policies, setPolicies] = useState([]);
  const [selectedPolicy, setSelectedPolicy] = useState(null);
  const [loading, setLoading] = useState(true);

  // Ingestion state
  const [instruction, setInstruction] = useState('');
  const [file, setFile] = useState(null);
  const [ingesting, setIngesting] = useState(false);
  const [ingestResult, setIngestResult] = useState(null);
  const [effectiveDateInput, setEffectiveDateInput] = useState('2027-01-01');

  // Approval state
  const [approving, setApproving] = useState(false);
  const [actionNotice, setActionNotice] = useState(null);

  // Collapsible JSON
  const [showJson, setShowJson] = useState(false);

  const loadPolicies = async () => {
    setLoading(true);
    try {
      const data = await fetchAllPolicies();
      setPolicies(data);
      if (data.length > 0) {
        const detail = await fetchPolicyDetail(data[0].id);
        setSelectedPolicy(detail);
      }
    } catch (err) {
      console.error('Error fetching policies', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPolicies();
  }, []);

  const handleSelectPolicy = async (p) => {
    try {
      const detail = await fetchPolicyDetail(p.id);
      setSelectedPolicy(detail);
      setIngestResult(null);
    } catch (err) {
      alert(`Failed to load policy: ${err.message}`);
    }
  };

  const handleIngest = async () => {
    if (!instruction.trim() && !file) return;

    setIngesting(true);
    setIngestResult(null);
    try {
      let payload;
      if (file) {
        payload = new FormData();
        payload.append('file', file);
      } else {
        payload = { instruction };
      }

      const res = await ingestPolicy(payload);
      setIngestResult(res);
      setEffectiveDateInput(res.effective_from || '2027-01-01');
      await loadPolicies();
    } catch (err) {
      alert(`Ingestion failed: ${err.message}`);
    } finally {
      setIngesting(false);
    }
  };

  const handleApproveAndActivate = async () => {
    const targetId = ingestResult ? ingestResult.draft_id : selectedPolicy?.id;
    if (!targetId) return;

    setApproving(true);
    try {
      const res = await approvePolicy(targetId, {
        approved_by: 'Procurement Admin',
        comment: 'Approved after structural review and impact preview',
      });
      setActionNotice(res.message);
      setIngestResult(null);
      await loadPolicies();
      if (onPolicyActivated) onPolicyActivated();
      setTimeout(() => setActionNotice(null), 5000);
    } catch (err) {
      alert(`Approval error: ${err.message}`);
    } finally {
      setApproving(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Notice Banner */}
      {actionNotice && (
        <div className="p-4 bg-emerald-50 border border-emerald-300 text-emerald-800 rounded-xl text-xs flex items-center space-x-2 shadow-sm">
          <CheckCircle className="w-5 h-5 text-emerald-600 flex-shrink-0" />
          <span className="font-semibold">{actionNotice}</span>
        </div>
      )}

      {/* Main Grid: Timeline + Ingestion & Preview */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Col: Timeline & History */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 space-y-4">
          <div className="flex items-center space-x-2 border-b border-slate-200 pb-3">
            <Clock className="w-4 h-4 text-sky-600" />
            <h3 className="text-sm font-bold text-slate-900">Policy Versions Timeline</h3>
          </div>

          <div className="space-y-3">
            {policies.map((p) => {
              const isSelected = selectedPolicy?.id === p.id;
              const isActive = p.status === 'ACTIVE';
              return (
                <div
                  key={p.id}
                  onClick={() => handleSelectPolicy(p)}
                  className={`p-3 rounded-lg border text-xs cursor-pointer transition-all ${
                    isSelected
                      ? 'border-sky-500 bg-sky-50/50 shadow-xs'
                      : 'border-slate-200 hover:border-slate-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-900 text-sm">{p.version_label}</span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                        isActive
                          ? 'bg-emerald-100 text-emerald-800'
                          : p.status === 'DRAFT'
                          ? 'bg-amber-100 text-amber-800'
                          : 'bg-slate-100 text-slate-600'
                      }`}
                    >
                      {p.status}
                    </span>
                  </div>
                  <div className="mt-1 text-slate-500">Effective: {p.effective_from}</div>
                  <div className="mt-0.5 text-slate-400 text-[11px]">By {p.created_by}</div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Center & Right Col: Amendment Ingestion & Impact Preview */}
        <div className="lg:col-span-2 space-y-6">
          {/* Amendment Input Box */}
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-4">
            <div className="border-b border-slate-200 pb-3">
              <h3 className="text-sm font-bold text-slate-900">Upload Policy Amendment</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Upload amendment document (.pdf, .docx, .txt) or enter natural-language instruction (e.g. 'Raise spot limit to Rs 3,00,000 for CHK1').
              </p>
            </div>

            <div className="space-y-3">
              <textarea
                rows={2}
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                placeholder="Type amendment instruction or paste policy change text..."
                className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
              />

              <div className="flex items-center justify-between gap-4">
                <input
                  type="file"
                  accept=".pdf,.docx,.txt"
                  onChange={(e) => setFile(e.target.files[0])}
                  className="text-xs text-slate-500 file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-medium file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200"
                />

                <button
                  onClick={handleIngest}
                  disabled={ingesting || (!instruction.trim() && !file)}
                  className="px-5 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white font-medium text-xs flex items-center space-x-1.5 transition-colors cursor-pointer"
                >
                  <Upload className="w-3.5 h-3.5" />
                  <span>{ingesting ? 'Analyzing...' : 'Analyze Amendment'}</span>
                </button>
              </div>
            </div>
          </div>

          {/* Diff & Impact Preview Card */}
          {ingestResult ? (
            <div className="bg-white rounded-xl shadow-sm border-2 border-sky-400 p-6 space-y-5">
              <div className="flex items-center justify-between border-b border-slate-200 pb-3">
                <div>
                  <span className="text-[11px] font-bold text-sky-700 uppercase tracking-wider block">
                    Proposed Amendment Draft
                  </span>
                  <h4 className="text-base font-bold text-slate-900">
                    Draft {ingestResult.version_label}
                  </h4>
                </div>
                <div className="text-right">
                  <span className="text-xs text-slate-500">Effective Date:</span>
                  <input
                    type="date"
                    value={effectiveDateInput}
                    onChange={(e) => setEffectiveDateInput(e.target.value)}
                    className="ml-2 px-2 py-1 bg-slate-50 border border-slate-200 rounded text-xs text-slate-900"
                  />
                </div>
              </div>

              {/* Plain-Language Diff */}
              <div className="p-4 bg-sky-50 border border-sky-200 rounded-xl space-y-2">
                <span className="text-[11px] font-bold text-sky-900 uppercase tracking-wider block">
                  Plain-Language Diff
                </span>
                <p className="text-xs text-slate-800 font-medium leading-relaxed">
                  {ingestResult.diff_summary}
                </p>
                {ingestResult.diff_details && ingestResult.diff_details.length > 0 && (
                  <ul className="list-disc pl-4 text-xs text-slate-600 space-y-1 pt-1">
                    {ingestResult.diff_details.map((d, i) => (
                      <li key={i}>{typeof d === 'string' ? d : JSON.stringify(d)}</li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Impact Preview on Sample Batch */}
              {ingestResult.impact_preview && (
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
                  <span className="text-[11px] font-bold text-slate-800 uppercase tracking-wider block">
                    Batch Rehearsal & Impact Preview
                  </span>
                  <p className="text-xs text-slate-600">
                    {ingestResult.impact_preview.summary ||
                      `Re-evaluated sample batch: ${ingestResult.impact_preview.changed_count} line decisions altered.`}
                  </p>
                </div>
              )}

              {/* Primary Action Button */}
              <div className="pt-2 flex justify-end space-x-3">
                <button
                  onClick={() => setIngestResult(null)}
                  className="px-4 py-2.5 rounded-lg border border-slate-300 hover:bg-slate-100 text-slate-700 font-medium text-xs cursor-pointer"
                >
                  Discard Draft
                </button>
                <button
                  onClick={handleApproveAndActivate}
                  disabled={approving}
                  className="px-6 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-bold text-xs shadow-sm flex items-center space-x-2 transition-colors cursor-pointer"
                >
                  <CheckCircle className="w-4 h-4" />
                  <span>
                    {approving ? 'Activating...' : 'Approve & Activate with Effective Date'}
                  </span>
                </button>
              </div>
            </div>
          ) : selectedPolicy ? (
            /* Selected Policy Inspection Card */
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-200 pb-3">
                <div>
                  <h4 className="text-base font-bold text-slate-900">
                    Policy Version {selectedPolicy.version_label}
                  </h4>
                  <p className="text-xs text-slate-500">
                    Effective From: {selectedPolicy.effective_from} | Status: {selectedPolicy.status}
                  </p>
                </div>

                {selectedPolicy.status === 'DRAFT' && (
                  <button
                    onClick={handleApproveAndActivate}
                    disabled={approving}
                    className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs shadow-sm"
                  >
                    {approving ? 'Activating...' : 'Approve & Activate'}
                  </button>
                )}
              </div>

              {selectedPolicy.diff_summary && (
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-700">
                  <span className="font-semibold block mb-0.5">Version Diff Summary:</span>
                  {selectedPolicy.diff_summary}
                </div>
              )}

              {/* Collapsible Raw JSON */}
              <div className="pt-2 border-t border-slate-100">
                <button
                  onClick={() => setShowJson(!showJson)}
                  className="flex items-center space-x-1.5 text-xs text-sky-600 hover:text-sky-800 font-semibold cursor-pointer"
                >
                  {showJson ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  <span>{showJson ? 'Hide' : 'Show'} Raw Policy JSON</span>
                </button>

                {showJson && (
                  <pre className="mt-3 p-4 bg-slate-900 text-slate-100 rounded-lg text-[11px] overflow-x-auto max-h-96">
                    {JSON.stringify(selectedPolicy.rules, null, 2)}
                  </pre>
                )}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}


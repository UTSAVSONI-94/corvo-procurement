import React, { useState, useEffect } from 'react';
import {
  FileText,
  Upload,
  Plus,
  Search,
  CheckCircle,
  AlertCircle,
  X,
  ExternalLink,
  ShieldCheck,
} from 'lucide-react';
import { fetchContracts, extractContractPdf, confirmContract, manualContract } from '../api';

export default function ContractsView() {
  const [contracts, setContracts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');

  // Modal states: "UPLOAD_PDF" or "MANUAL_ENTRY"
  const [modalMode, setModalMode] = useState(null);
  const [pdfFile, setPdfFile] = useState(null);
  const [extracting, setExtracting] = useState(false);
  const [previewData, setPreviewData] = useState(null);
  const [saving, setSaving] = useState(false);
  const [actionNotice, setActionNotice] = useState(null);

  // Manual Form fields
  const [manualContractId, setManualContractId] = useState('');
  const [manualSupplierId, setManualSupplierId] = useState('');
  const [manualSupplierName, setManualSupplierName] = useState('');
  const [manualStartDate, setManualStartDate] = useState('2026-01-01');
  const [manualEndDate, setManualEndDate] = useState('2026-12-31');
  const [manualCeiling, setManualCeiling] = useState('1000000');
  const [manualLines, setManualLines] = useState([
    { item_code: 'ITM-1001', description: 'Deep groove ball bearing 6205', uom: 'EA', rate: 250.0 },
  ]);

  const loadContracts = async () => {
    setLoading(true);
    try {
      const data = await fetchContracts({ search, status: statusFilter });
      setContracts(data);
    } catch (err) {
      console.error('Error fetching contracts', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadContracts();
  }, [statusFilter]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    loadContracts();
  };

  const handleExtractPdf = async () => {
    if (!pdfFile) return;
    setExtracting(true);
    try {
      const preview = await extractContractPdf(pdfFile);
      setPreviewData(preview);
    } catch (err) {
      alert(`Extraction failed: ${err.message}`);
    } finally {
      setExtracting(false);
    }
  };

  const handleConfirmExtracted = async () => {
    if (!previewData) return;
    setSaving(true);
    try {
      const res = await confirmContract({
        contract_id: previewData.contract_id,
        supplier_id: previewData.supplier_id,
        supplier_name: previewData.supplier_name,
        start_date: previewData.start_date,
        end_date: previewData.end_date,
        value_ceiling: previewData.value_ceiling,
        source: 'PDF_EXTRACTED',
        pdf_path: previewData.pdf_path,
        lines: previewData.lines,
      });
      setActionNotice(res.message);
      setModalMode(null);
      setPreviewData(null);
      setPdfFile(null);
      loadContracts();
      setTimeout(() => setActionNotice(null), 4000);
    } catch (err) {
      alert(`Save error: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveManual = async () => {
    if (!manualContractId || !manualSupplierId) {
      alert('Contract ID and Supplier ID are required');
      return;
    }
    setSaving(true);
    try {
      const res = await manualContract({
        contract_id: manualContractId,
        supplier_id: manualSupplierId,
        supplier_name: manualSupplierName || manualSupplierId,
        start_date: manualStartDate,
        end_date: manualEndDate,
        value_ceiling: parseFloat(manualCeiling),
        source: 'PDF_MANUAL',
        lines: manualLines,
      });
      setActionNotice(res.message);
      setModalMode(null);
      loadContracts();
      setTimeout(() => setActionNotice(null), 4000);
    } catch (err) {
      alert(`Manual save error: ${err.message}`);
    } finally {
      setSaving(false);
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

      {/* Control Bar: Filters & Primary Action */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
        {/* Search & Status Filter */}
        <form onSubmit={handleSearchSubmit} className="flex items-center space-x-3 flex-1 max-w-lg">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search contract ID, supplier, item code..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 focus:bg-white text-slate-900"
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-700 focus:outline-none"
          >
            <option value="ALL">All Statuses</option>
            <option value="ACTIVE">ACTIVE</option>
            <option value="EXPIRED">EXPIRED</option>
            <option value="EXHAUSTED">EXHAUSTED</option>
          </select>
        </form>

        {/* Primary Action Button */}
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setModalMode('MANUAL_ENTRY')}
            className="px-4 py-2.5 rounded-lg border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-semibold cursor-pointer"
          >
            Manual Entry
          </button>
          <button
            onClick={() => setModalMode('UPLOAD_PDF')}
            className="px-5 py-2.5 rounded-lg bg-sky-600 hover:bg-sky-700 text-white text-xs font-semibold shadow-sm flex items-center space-x-2 cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            <span>Add contract</span>
          </button>
        </div>
      </div>

      {/* Contracts Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-slate-400 text-sm">
            <div className="animate-spin w-6 h-6 border-2 border-sky-600 border-t-transparent rounded-full mx-auto mb-2"></div>
            Loading active contract register...
          </div>
        ) : contracts.length === 0 ? (
          <div className="p-12 text-center text-slate-400 text-sm">
            No contracts found matching your filters.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-600 uppercase font-semibold border-b border-slate-200">
                <tr>
                  <th className="px-6 py-3">Contract ID</th>
                  <th className="px-6 py-3">Supplier ID & Name</th>
                  <th className="px-6 py-3">Validity Period</th>
                  <th className="px-6 py-3">Ceiling Utilization</th>
                  <th className="px-6 py-3 text-right">Ceiling / Consumed (INR)</th>
                  <th className="px-6 py-3 text-center">Items</th>
                  <th className="px-6 py-3">Source</th>
                  <th className="px-6 py-3 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 text-slate-700">
                {contracts.map((c) => {
                  let statusBadgeClass = 'bg-emerald-100 text-emerald-800';
                  if (c.validity_status === 'EXPIRED') statusBadgeClass = 'bg-slate-100 text-slate-700';
                  if (c.validity_status === 'EXHAUSTED') statusBadgeClass = 'bg-rose-100 text-rose-800';

                  return (
                    <tr key={c.contract_id} className="hover:bg-slate-50/70">
                      <td className="px-6 py-4 font-mono font-bold text-slate-900">
                        {c.contract_id}
                      </td>
                      <td className="px-6 py-4">
                        <div className="font-semibold text-slate-900">{c.supplier_name}</div>
                        <div className="font-mono text-[11px] text-slate-500">{c.supplier_id}</div>
                      </td>
                      <td className="px-6 py-4 text-slate-600">
                        <div>{c.start_date} to {c.end_date}</div>
                      </td>
                      <td className="px-6 py-4 w-48">
                        <div className="flex justify-between text-[11px] font-semibold text-slate-700 mb-1">
                          <span>{c.ceiling_used_pct}%</span>
                          <span className="text-slate-400">Rem: ₹{c.remaining_value.toLocaleString('en-IN')}</span>
                        </div>
                        <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                          <div
                            className={`h-2 rounded-full ${
                              c.ceiling_used_pct >= 90
                                ? 'bg-rose-500'
                                : c.ceiling_used_pct >= 75
                                ? 'bg-amber-500'
                                : 'bg-emerald-500'
                            }`}
                            style={{ width: `${Math.min(c.ceiling_used_pct, 100)}%` }}
                          ></div>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <div className="font-semibold text-slate-900">
                          ₹{c.value_ceiling.toLocaleString('en-IN')}
                        </div>
                        <div className="text-slate-500 text-[11px]">
                          Used: ₹{c.consumed_value.toLocaleString('en-IN')}
                        </div>
                      </td>
                      <td className="px-6 py-4 text-center font-semibold text-slate-700">
                        {c.lines_count}
                      </td>
                      <td className="px-6 py-4">
                        <span className="inline-block px-2 py-0.5 rounded text-[10px] font-mono bg-slate-100 text-slate-600">
                          {c.source}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <span
                          className={`inline-block px-2.5 py-0.5 rounded-full text-[10px] font-bold ${statusBadgeClass}`}
                        >
                          {c.validity_status}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Upload PDF & Extraction Preview Modal */}
      {modalMode === 'UPLOAD_PDF' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-xl shadow-2xl border border-slate-200 max-w-2xl w-full p-6 space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200">
              <h3 className="text-base font-bold text-slate-900">Upload Contract PDF</h3>
              <button
                onClick={() => {
                  setModalMode(null);
                  setPreviewData(null);
                }}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {!previewData ? (
              <div className="space-y-4 text-center py-6">
                <input
                  type="file"
                  accept=".pdf"
                  onChange={(e) => setPdfFile(e.target.files[0])}
                  className="text-xs text-slate-500 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-sky-50 file:text-sky-700 hover:file:bg-sky-100 cursor-pointer"
                />
                <div>
                  <button
                    onClick={handleExtractPdf}
                    disabled={!pdfFile || extracting}
                    className="px-6 py-2.5 rounded-lg bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white font-semibold text-xs shadow-sm cursor-pointer"
                  >
                    {extracting ? 'Extracting Metadata & Schedule A...' : 'Extract Contract'}
                  </button>
                </div>
              </div>
            ) : (
              /* Extraction Preview Form (Editable) */
              <div className="space-y-4 text-xs">
                <div className="p-3 bg-sky-50 border border-sky-200 rounded-lg text-sky-800">
                  <span className="font-bold">Confidence Score: {(previewData.confidence_score * 100).toFixed(0)}%</span>
                  <p className="mt-0.5 text-slate-600">{previewData.confidence_note}</p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-700 font-medium mb-1">Contract ID</label>
                    <input
                      type="text"
                      value={previewData.contract_id}
                      onChange={(e) => setPreviewData({ ...previewData, contract_id: e.target.value })}
                      className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded text-slate-900 font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-700 font-medium mb-1">Supplier ID</label>
                    <input
                      type="text"
                      value={previewData.supplier_id}
                      onChange={(e) => setPreviewData({ ...previewData, supplier_id: e.target.value })}
                      className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded text-slate-900 font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-700 font-medium mb-1">Start Date</label>
                    <input
                      type="date"
                      value={previewData.start_date}
                      onChange={(e) => setPreviewData({ ...previewData, start_date: e.target.value })}
                      className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded text-slate-900"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-700 font-medium mb-1">End Date</label>
                    <input
                      type="date"
                      value={previewData.end_date}
                      onChange={(e) => setPreviewData({ ...previewData, end_date: e.target.value })}
                      className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded text-slate-900"
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="block text-slate-700 font-medium mb-1">Value Ceiling (INR)</label>
                    <input
                      type="number"
                      value={previewData.value_ceiling}
                      onChange={(e) => setPreviewData({ ...previewData, value_ceiling: parseFloat(e.target.value) || 0 })}
                      className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded text-slate-900"
                    />
                  </div>
                </div>

                <div>
                  <h4 className="font-semibold text-slate-800 mb-2">Schedule A Line Items ({previewData.lines.length})</h4>
                  <div className="border border-slate-200 rounded-lg overflow-hidden">
                    <table className="w-full text-left text-[11px]">
                      <thead className="bg-slate-50 font-semibold text-slate-600 border-b">
                        <tr>
                          <th className="px-3 py-2">Item Code</th>
                          <th className="px-3 py-2">Description</th>
                          <th className="px-3 py-2">UoM</th>
                          <th className="px-3 py-2 text-right">Contract Rate (INR)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {previewData.lines.map((l, idx) => (
                          <tr key={idx}>
                            <td className="px-3 py-1.5 font-mono font-medium">{l.item_code}</td>
                            <td className="px-3 py-1.5 text-slate-600">{l.description}</td>
                            <td className="px-3 py-1.5">{l.uom}</td>
                            <td className="px-3 py-1.5 text-right font-bold text-sky-700">₹{l.rate.toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="pt-3 border-t border-slate-200 flex justify-end space-x-3">
                  <button
                    onClick={() => setPreviewData(null)}
                    className="px-4 py-2 rounded-lg border border-slate-300 hover:bg-slate-50 text-slate-700"
                  >
                    Back
                  </button>
                  <button
                    onClick={handleConfirmExtracted}
                    disabled={saving}
                    className="px-6 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-bold shadow-sm"
                  >
                    {saving ? 'Confirming...' : 'Confirm and Save into Active Register'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Manual Contract Entry Modal */}
      {modalMode === 'MANUAL_ENTRY' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-xl shadow-2xl border border-slate-200 max-w-lg w-full p-6 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200">
              <h3 className="text-base font-bold text-slate-900">Manual Contract Entry</h3>
              <button onClick={() => setModalMode(null)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-medium mb-1">Contract ID</label>
                  <input
                    type="text"
                    value={manualContractId}
                    onChange={(e) => setManualContractId(e.target.value)}
                    placeholder="e.g. RC-2026-099"
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-900 font-mono"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-medium mb-1">Supplier ID</label>
                  <input
                    type="text"
                    value={manualSupplierId}
                    onChange={(e) => setManualSupplierId(e.target.value)}
                    placeholder="e.g. S002"
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-900 font-mono"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-medium mb-1">Start Date</label>
                  <input
                    type="date"
                    value={manualStartDate}
                    onChange={(e) => setManualStartDate(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-900"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-medium mb-1">End Date</label>
                  <input
                    type="date"
                    value={manualEndDate}
                    onChange={(e) => setManualEndDate(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-900"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-700 font-medium mb-1">Value Ceiling (INR)</label>
                <input
                  type="number"
                  value={manualCeiling}
                  onChange={(e) => setManualCeiling(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-900"
                />
              </div>
            </div>

            <div className="pt-3 border-t border-slate-200 flex justify-end space-x-3">
              <button
                onClick={() => setModalMode(null)}
                className="px-4 py-2 rounded-lg border border-slate-300 text-slate-700 text-xs font-medium"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveManual}
                disabled={saving || !manualContractId || !manualSupplierId}
                className="px-5 py-2 rounded-lg bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white font-semibold text-xs shadow-sm"
              >
                {saving ? 'Saving...' : 'Save Contract'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


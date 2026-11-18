import React, { useState } from 'react';
import { Upload, CheckCircle, AlertTriangle, FileText, ArrowRight, Download, RefreshCw } from 'lucide-react';
import { uploadPrBatch, processBatch } from '../api';

export default function BatchesView({ onBatchProcessed }) {
  const [file, setFile] = useState(null);
  const [validating, setValidating] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [validationResult, setValidationResult] = useState(null);
  const [batchOutput, setBatchOutput] = useState(null);
  const [error, setError] = useState(null);

  const [history, setHistory] = useState([
    {
      id: 'BATCH-202611-01',
      date: '2026-11-18 10:15',
      filename: 'sample_pr_batch.csv',
      lines: 186,
      status: 'PROCESSED',
      pos_created: 14,
    },
  ]);

  const handleFileChange = (e) => {
    const f = e.target.files[0];
    if (f) {
      setFile(f);
      setValidationResult(null);
      setBatchOutput(null);
      setError(null);
    }
  };

  const handleProcessBatch = async () => {
    if (!file) return;
    setError(null);
    setProcessing(true);

    try {
      // 1. Validate lines
      const valRes = await uploadPrBatch(file);
      setValidationResult(valRes);

      // 2. Process through pure engine
      const out = await processBatch(file);
      setBatchOutput(out);

      // Append to history
      setHistory((prev) => [
        {
          id: `BATCH-${Date.now().toString().slice(-6)}`,
          date: new Date().toISOString().replace('T', ' ').slice(0, 16),
          filename: file.name,
          lines: out.total_lines,
          status: 'PROCESSED',
          pos_created: new Set(out.lines.map((l) => l.po_id).filter(Boolean)).size,
        },
        ...prev,
      ]);

      if (onBatchProcessed) onBatchProcessed(out);
    } catch (err) {
      setError(err.message || 'Error processing batch file');
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      {/* Upload & Action Card */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8">
        <div className="max-w-2xl mx-auto text-center space-y-4">
          <div className="w-12 h-12 mx-auto rounded-full bg-sky-50 border border-sky-100 flex items-center justify-center text-sky-600">
            <Upload className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-slate-900">Upload Procurement Batch CSV</h2>
            <p className="text-sm text-slate-500 mt-1">
              Upload raw requisition lines to validate schemas, club lines, and route decisions.
            </p>
          </div>

          {/* File Picker */}
          <div className="mt-6 flex flex-col items-center justify-center">
            <label className="flex flex-col items-center justify-center w-full h-36 border-2 border-dashed border-slate-300 rounded-xl cursor-pointer hover:border-sky-500 hover:bg-sky-50/50 transition-all">
              <div className="flex flex-col items-center justify-center pt-5 pb-6">
                <FileText className="w-8 h-8 text-slate-400 mb-2" />
                <p className="text-sm text-slate-600">
                  <span className="font-semibold text-sky-600">Click to browse</span> or drag and drop
                </p>
                <p className="text-xs text-slate-400 mt-1">
                  {file ? file.name : 'CSV files up to 10MB'}
                </p>
              </div>
            </label>
            <input
              data-testid="batch-file-input"
              type="file"
              accept=".csv"
              className="mt-2 text-xs text-slate-500"
              onChange={handleFileChange}
            />
          </div>

          {/* Error Message */}
          {error && (
            <div className="p-4 bg-rose-50 border border-rose-200 text-rose-700 rounded-lg text-sm flex items-center space-x-2 text-left">
              <AlertTriangle className="w-5 h-5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Primary Action Button */}
          <div className="pt-4 flex justify-center">
            <button
              onClick={handleProcessBatch}
              disabled={!file || processing}
              className="px-8 py-3 rounded-lg bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white font-semibold text-sm shadow-sm flex items-center space-x-2 transition-all cursor-pointer"
            >
              {processing ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Processing Batch...</span>
                </>
              ) : (
                <>
                  <span>Process batch</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        </div>

        {/* Validation and Processing Summary */}
        {validationResult && batchOutput && (
          <div className="mt-8 pt-8 border-t border-slate-200 grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
              <span className="text-xs text-slate-500 font-medium uppercase tracking-wider">
                Total Rows Evaluated
              </span>
              <p className="text-2xl font-bold text-slate-900 mt-1">
                {validationResult.total_rows}
              </p>
              <span className="text-xs text-slate-500 mt-1 block">
                {validationResult.accepted_count} accepted, {validationResult.rejected_count} rejected
              </span>
            </div>

            <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-lg">
              <span className="text-xs text-emerald-700 font-medium uppercase tracking-wider">
                POs Generated
              </span>
              <p className="text-2xl font-bold text-emerald-900 mt-1">
                {new Set(batchOutput.lines.map((l) => l.po_id).filter(Boolean)).size}
              </p>
              <span className="text-xs text-emerald-600 mt-1 block">
                Consolidated within 24h window
              </span>
            </div>

            <div className="p-4 bg-sky-50 border border-sky-200 rounded-lg">
              <span className="text-xs text-sky-700 font-medium uppercase tracking-wider">
                Sourcing Requests
              </span>
              <p className="text-2xl font-bold text-sky-900 mt-1">
                {batchOutput.lines.filter((l) => l.decision === 'SOURCING_REQUEST').length}
              </p>
              <span className="text-xs text-sky-600 mt-1 block">
                Routed to RFQ / RFP / Capex
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Batch Processing History */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-800">Previous Batches</h3>
          <span className="text-xs text-slate-500">{history.length} batches recorded</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-600 uppercase font-semibold border-b border-slate-200">
              <tr>
                <th className="px-6 py-3">Batch ID</th>
                <th className="px-6 py-3">Timestamp</th>
                <th className="px-6 py-3">Filename</th>
                <th className="px-6 py-3 text-right">PR Lines</th>
                <th className="px-6 py-3 text-right">POs Created</th>
                <th className="px-6 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-slate-700">
              {history.map((h, i) => (
                <tr key={i} className="hover:bg-slate-50/50">
                  <td className="px-6 py-3 font-mono font-medium text-slate-900">{h.id}</td>
                  <td className="px-6 py-3 text-slate-500">{h.date}</td>
                  <td className="px-6 py-3">{h.filename}</td>
                  <td className="px-6 py-3 text-right font-medium">{h.lines}</td>
                  <td className="px-6 py-3 text-right font-medium text-emerald-600">
                    {h.pos_created}
                  </td>
                  <td className="px-6 py-3">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">
                      {h.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}


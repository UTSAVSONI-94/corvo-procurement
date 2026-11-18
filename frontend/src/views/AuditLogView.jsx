import React, { useState, useEffect } from 'react';
import { ShieldCheck, Filter, Search, Clock, User, Tag } from 'lucide-react';
import { fetchAuditLogs } from '../api';

export default function AuditLogView() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [entityFilter, setEntityFilter] = useState('ALL');
  const [actionFilter, setActionFilter] = useState('ALL');
  const [whoSearch, setWhoSearch] = useState('');

  const loadLogs = async () => {
    setLoading(true);
    try {
      const data = await fetchAuditLogs({
        entity: entityFilter,
        action: actionFilter,
        who: whoSearch,
      });
      setLogs(data);
    } catch (err) {
      console.error('Error fetching audit logs', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, [entityFilter, actionFilter]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    loadLogs();
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Control Bar */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-slate-900">Procurement Audit Trails</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Immutable system log tracking who, when, what, and before/after state changes across policies, contracts, and decisions.
          </p>
        </div>

        {/* Filter Controls */}
        <form onSubmit={handleSearchSubmit} className="flex flex-wrap items-center gap-2 text-xs">
          <input
            type="text"
            placeholder="Filter by actor (e.g. Buyer, Admin)..."
            value={whoSearch}
            onChange={(e) => setWhoSearch(e.target.value)}
            className="px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-slate-900 focus:outline-none"
          />

          <select
            value={entityFilter}
            onChange={(e) => setEntityFilter(e.target.value)}
            className="px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-slate-700 focus:outline-none"
          >
            <option value="ALL">All Entities</option>
            <option value="POLICY">POLICY</option>
            <option value="CONTRACT">CONTRACT</option>
            <option value="REQUIREMENT">REQUIREMENT</option>
            <option value="DECISION">DECISION</option>
          </select>

          <select
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            className="px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-slate-700 focus:outline-none"
          >
            <option value="ALL">All Actions</option>
            <option value="APPROVE">APPROVE</option>
            <option value="OVERRIDE">OVERRIDE</option>
            <option value="INGEST">INGEST</option>
            <option value="CREATE">CREATE</option>
          </select>

          <button
            type="submit"
            className="px-4 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-700 text-white font-medium cursor-pointer"
          >
            Filter
          </button>
        </form>
      </div>

      {/* Logs Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-slate-400 text-sm">
            <div className="animate-spin w-6 h-6 border-2 border-sky-600 border-t-transparent rounded-full mx-auto mb-2"></div>
            Loading audit trails...
          </div>
        ) : logs.length === 0 ? (
          <div className="p-12 text-center text-slate-400 text-sm">
            No audit records match your filters.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-600 uppercase font-semibold border-b border-slate-200">
                <tr>
                  <th className="px-6 py-3">Timestamp</th>
                  <th className="px-6 py-3">Actor (Who)</th>
                  <th className="px-6 py-3">Action</th>
                  <th className="px-6 py-3">Entity</th>
                  <th className="px-6 py-3">Target ID</th>
                  <th className="px-6 py-3">State Transition (Before → After)</th>
                  <th className="px-6 py-3">Comment / Justification</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 text-slate-700">
                {logs.map((l) => {
                  let actionBadge = 'bg-slate-100 text-slate-700';
                  if (l.action === 'APPROVE') actionBadge = 'bg-emerald-100 text-emerald-800';
                  if (l.action === 'OVERRIDE') actionBadge = 'bg-amber-100 text-amber-800';
                  if (l.action === 'INGEST') actionBadge = 'bg-sky-100 text-sky-800';

                  return (
                    <tr key={l.id} className="hover:bg-slate-50/70">
                      <td className="px-6 py-3.5 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                        {l.when_timestamp}
                      </td>
                      <td className="px-6 py-3.5 font-medium text-slate-900">
                        {l.who}
                      </td>
                      <td className="px-6 py-3.5">
                        <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold ${actionBadge}`}>
                          {l.action}
                        </span>
                      </td>
                      <td className="px-6 py-3.5 font-semibold text-slate-700">
                        {l.entity}
                      </td>
                      <td className="px-6 py-3.5 font-mono text-slate-900">
                        {l.entity_id || '—'}
                      </td>
                      <td className="px-6 py-3.5 text-slate-600 max-w-xs truncate">
                        <span className="font-mono text-[11px] text-slate-500">{l.before_state || 'none'}</span>
                        <span className="mx-1 text-slate-400">→</span>
                        <span className="font-mono text-[11px] font-semibold text-slate-800">{l.after_state}</span>
                      </td>
                      <td className="px-6 py-3.5 text-slate-600 max-w-sm truncate" title={l.comment}>
                        {l.comment || '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}


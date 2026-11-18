import React, { useState, useEffect } from 'react';
import {
  Search,
  Filter,
  CheckCircle,
  Edit3,
  ChevronDown,
  ChevronRight,
  X,
  FileText,
  AlertCircle,
  ExternalLink,
  Layers,
  Building,
  DollarSign,
  TrendingUp,
} from 'lucide-react';
import { fetchRequirements, approveRequirements, overrideRequirement } from '../api';

export default function BuyerWorkspace() {
  const [requirements, setRequirements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters
  const [search, setSearch] = useState('');
  const [routeFilter, setRouteFilter] = useState('ALL');
  const [plantFilter, setPlantFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');

  // Expansion & Selection
  const [expandedGroups, setExpandedGroups] = useState(new Set());
  const [selectedGroups, setSelectedGroups] = useState(new Set());

  // Detail Drawer ("Why")
  const [activeDrawer, setActiveDrawer] = useState(null);

  // Override Modal
  const [overrideTarget, setOverrideTarget] = useState(null);
  const [overrideRoute, setOverrideRoute] = useState('');
  const [overrideSupplier, setOverrideSupplier] = useState('');
  const [overridePrice, setOverridePrice] = useState('');
  const [overrideComment, setOverrideComment] = useState('');
  const [overrideSubmitting, setOverrideSubmitting] = useState(false);

  // Action status notification
  const [actionNotice, setActionNotice] = useState(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchRequirements();
      setRequirements(res.requirements || []);
    } catch (err) {
      setError(err.message || 'Failed to load requirements');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const toggleExpand = (gid) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(gid)) next.delete(gid);
      else next.add(gid);
      return next;
    });
  };

  const toggleSelectRow = (gid) => {
    setSelectedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(gid)) next.delete(gid);
      else next.add(gid);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedGroups.size === filteredRequirements.length) {
      setSelectedGroups(new Set());
    } else {
      setSelectedGroups(new Set(filteredRequirements.map((r) => r.group_id)));
    }
  };

  const handleBulkApprove = async () => {
    if (selectedGroups.size === 0) return;
    try {
      const res = await approveRequirements(Array.from(selectedGroups), 'Buyer');
      setActionNotice(res.message);
      setSelectedGroups(new Set());
      loadData();
      setTimeout(() => setActionNotice(null), 4000);
    } catch (err) {
      alert(`Approval failed: ${err.message}`);
    }
  };

  const handleApproveSingle = async (gid) => {
    try {
      const res = await approveRequirements([gid], 'Buyer');
      setActionNotice(res.message);
      loadData();
      setTimeout(() => setActionNotice(null), 4000);
    } catch (err) {
      alert(`Approval failed: ${err.message}`);
    }
  };

  const handleOpenOverride = (req) => {
    setOverrideTarget(req);
    setOverrideRoute(req.route);
    setOverrideSupplier(req.supplier_id || '');
    setOverridePrice(req.unit_price ? req.unit_price.toString() : '');
    setOverrideComment('');
  };

  const handleSaveOverride = async () => {
    if (!overrideComment.trim()) {
      alert('An override justification comment is strictly required.');
      return;
    }
    setOverrideSubmitting(true);
    try {
      await overrideRequirement(overrideTarget.group_id, {
        route: overrideRoute,
        supplier_id: overrideSupplier,
        unit_price: overridePrice ? parseFloat(overridePrice) : null,
        comment: overrideComment,
        overridden_by: 'Buyer',
      });
      setOverrideTarget(null);
      setActionNotice(`Requirement ${overrideTarget.group_id} overridden successfully.`);
      loadData();
      setTimeout(() => setActionNotice(null), 4000);
    } catch (err) {
      alert(`Override failed: ${err.message}`);
    } finally {
      setOverrideSubmitting(false);
    }
  };

  // Filter computation
  const filteredRequirements = requirements.filter((r) => {
    if (routeFilter !== 'ALL' && r.route !== routeFilter) return false;
    if (plantFilter !== 'ALL' && r.plant !== plantFilter) return false;
    if (statusFilter !== 'ALL' && r.status !== statusFilter) return false;
    if (search) {
      const s = search.toLowerCase();
      const matchGid = r.group_id.toLowerCase().includes(s);
      const matchItm = (r.item_code || '').toLowerCase().includes(s) || r.description.toLowerCase().includes(s);
      const matchSup = (r.supplier_id || '').toLowerCase().includes(s) || r.supplier_name.toLowerCase().includes(s);
      if (!matchGid && !matchItm && !matchSup) return false;
    }
    return true;
  });

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Action Notification */}
      {actionNotice && (
        <div className="p-4 bg-emerald-50 border border-emerald-300 text-emerald-800 rounded-xl text-sm flex items-center justify-between shadow-sm">
          <div className="flex items-center space-x-2">
            <CheckCircle className="w-5 h-5 text-emerald-600" />
            <span className="font-medium">{actionNotice}</span>
          </div>
          <button onClick={() => setActionNotice(null)} className="text-emerald-700 hover:text-emerald-900">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Control Bar: Filters & Bulk Actions */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          {/* Search */}
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
            <input
              type="text"
              placeholder="Search group ID, item, description, supplier..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 focus:bg-white transition-all text-slate-900"
            />
          </div>

          {/* Primary Action: Bulk Approve */}
          <div className="flex items-center space-x-3">
            <button
              data-testid="bulk-approve-btn"
              onClick={handleBulkApprove}
              disabled={selectedGroups.size === 0}
              className="px-5 py-2.5 rounded-lg bg-sky-600 hover:bg-sky-700 disabled:opacity-40 text-white font-medium text-xs shadow-sm flex items-center space-x-2 transition-colors cursor-pointer"
            >
              <CheckCircle className="w-4 h-4" />
              <span>Approve Selected ({selectedGroups.size})</span>
            </button>
          </div>
        </div>

        {/* Dropdown Filters */}
        <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-slate-100 text-xs">
          <div className="flex items-center space-x-1.5 text-slate-500">
            <Filter className="w-3.5 h-3.5" />
            <span>Filters:</span>
          </div>

          {/* Route Filter */}
          <select
            value={routeFilter}
            onChange={(e) => setRouteFilter(e.target.value)}
            className="px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-slate-700 focus:outline-none"
          >
            <option value="ALL">All Routes</option>
            <option value="CONTRACT_PO">CONTRACT_PO</option>
            <option value="SPOT_PO">SPOT_PO</option>
            <option value="RFQ">RFQ</option>
            <option value="RFP">RFP</option>
            <option value="CAPEX_SOURCING">CAPEX_SOURCING</option>
            <option value="NEW_ITEM_SOURCING">NEW_ITEM_SOURCING</option>
          </select>

          {/* Plant Filter */}
          <select
            value={plantFilter}
            onChange={(e) => setPlantFilter(e.target.value)}
            className="px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-slate-700 focus:outline-none"
          >
            <option value="ALL">All Plants</option>
            <option value="CHK1">Chakan (CHK1)</option>
            <option value="PUN1">Pune (PUN1)</option>
          </select>

          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-slate-700 focus:outline-none"
          >
            <option value="ALL">All Statuses</option>
            <option value="PENDING">PENDING</option>
            <option value="APPROVED">APPROVED</option>
          </select>

          {(routeFilter !== 'ALL' || plantFilter !== 'ALL' || statusFilter !== 'ALL' || search) && (
            <button
              onClick={() => {
                setRouteFilter('ALL');
                setPlantFilter('ALL');
                setStatusFilter('ALL');
                setSearch('');
              }}
              className="text-xs text-sky-600 hover:text-sky-800 font-medium ml-auto"
            >
              Reset Filters
            </button>
          )}
        </div>
      </div>

      {/* Main Requirements Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-slate-400 text-sm">
            <div className="animate-spin w-6 h-6 border-2 border-sky-600 border-t-transparent rounded-full mx-auto mb-2"></div>
            Loading requirements and policy decisions...
          </div>
        ) : filteredRequirements.length === 0 ? (
          <div className="p-12 text-center text-slate-400 text-sm">
            No requirements match the current filters.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-600 uppercase font-semibold border-b border-slate-200">
                <tr>
                  <th className="px-4 py-3 w-10">
                    <input
                      type="checkbox"
                      checked={
                        filteredRequirements.length > 0 &&
                        selectedGroups.size === filteredRequirements.length
                      }
                      onChange={toggleSelectAll}
                      className="rounded border-slate-300 text-sky-600 focus:ring-sky-500"
                    />
                  </th>
                  <th className="px-4 py-3">Group ID</th>
                  <th className="px-4 py-3">Item & Description</th>
                  <th className="px-4 py-3">Plant</th>
                  <th className="px-4 py-3 text-right">Value (INR)</th>
                  <th className="px-4 py-3 text-center">Lines</th>
                  <th className="px-4 py-3">Route / Decision</th>
                  <th className="px-4 py-3">Supplier & Price</th>
                  <th className="px-4 py-3">PO Reference</th>
                  <th className="px-4 py-3">Policy</th>
                  <th className="px-4 py-3 text-center">Status</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 text-slate-700">
                {filteredRequirements.map((r) => {
                  const isExpanded = expandedGroups.has(r.group_id);
                  const isSelected = selectedGroups.has(r.group_id);

                  // Route badge coloring
                  let routeBadgeClass = 'bg-slate-100 text-slate-700 border-slate-200';
                  if (r.route === 'CONTRACT_PO') routeBadgeClass = 'bg-blue-50 text-blue-700 border-blue-200';
                  else if (r.route === 'SPOT_PO') routeBadgeClass = 'bg-emerald-50 text-emerald-700 border-emerald-200';
                  else if (r.route === 'RFQ') routeBadgeClass = 'bg-amber-50 text-amber-700 border-amber-200';
                  else if (r.route === 'RFP') routeBadgeClass = 'bg-purple-50 text-purple-700 border-purple-200';
                  else if (r.route.includes('SOURCING')) routeBadgeClass = 'bg-rose-50 text-rose-700 border-rose-200';

                  return (
                    <React.Fragment key={r.group_id}>
                      <tr
                        className={`hover:bg-slate-50/70 transition-colors ${
                          isSelected ? 'bg-sky-50/40' : ''
                        }`}
                      >
                        <td className="px-4 py-3">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelectRow(r.group_id)}
                            className="rounded border-slate-300 text-sky-600 focus:ring-sky-500"
                          />
                        </td>
                        <td className="px-4 py-3 font-mono font-medium text-slate-900">
                          {r.group_id}
                        </td>
                        <td className="px-4 py-3 max-w-xs">
                          <div className="font-medium text-slate-900 truncate">
                            {r.item_code || 'NEW ITEM'}
                          </div>
                          <div className="text-slate-500 truncate text-[11px]">
                            {r.description}
                          </div>
                        </td>
                        <td className="px-4 py-3 font-semibold">{r.plant}</td>
                        <td className="px-4 py-3 text-right font-medium text-slate-900">
                          ₹{r.value_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>
                        <td className="px-4 py-3 text-center">
                          <button
                            onClick={() => toggleExpand(r.group_id)}
                            className="inline-flex items-center space-x-1 px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold"
                          >
                            <span>{r.lines.length}</span>
                            {isExpanded ? (
                              <ChevronDown className="w-3 h-3" />
                            ) : (
                              <ChevronRight className="w-3 h-3" />
                            )}
                          </button>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-block px-2.5 py-1 rounded-full text-[11px] font-semibold border ${routeBadgeClass}`}
                          >
                            {r.route}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          {r.supplier_name ? (
                            <div>
                              <div className="font-medium text-slate-900">{r.supplier_name}</div>
                              {r.unit_price && (
                                <div className="text-slate-500 text-[11px]">
                                  @ ₹{r.unit_price.toFixed(2)}/u
                                </div>
                              )}
                            </div>
                          ) : r.suggested_suppliers && r.suggested_suppliers.length > 0 ? (
                            <div className="text-slate-600 text-[11px]">
                              {r.suggested_suppliers.map((s) => s.supplier_id).join(', ')}
                            </div>
                          ) : (
                            <span className="text-slate-400 italic">None</span>
                          )}
                        </td>
                        <td className="px-4 py-3 font-mono text-[11px] text-slate-600">
                          {r.po_id ? (
                            <span className="text-sky-700 font-semibold">{r.po_id}</span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="px-4 py-3 text-slate-500 font-mono text-[11px]">
                          {r.policy_version}
                        </td>
                        <td className="px-4 py-3 text-center">
                          <span
                            className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                              r.status === 'APPROVED'
                                ? 'bg-emerald-100 text-emerald-800'
                                : 'bg-amber-100 text-amber-800'
                            }`}
                          >
                            {r.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right space-x-1 whitespace-nowrap">
                          {/* "Why" Drawer Trigger */}
                          <button
                            onClick={() => setActiveDrawer(r)}
                            className="px-2.5 py-1 rounded border border-slate-300 hover:bg-slate-100 text-slate-700 text-xs font-medium cursor-pointer"
                          >
                            Why
                          </button>
                          {/* Single Approve */}
                          <button
                            data-testid={`approve-btn-${r.group_id}`}
                            onClick={() => handleApproveSingle(r.group_id)}
                            className="px-2.5 py-1 rounded bg-sky-600 hover:bg-sky-700 text-white text-xs font-medium cursor-pointer"
                          >
                            Approve
                          </button>
                          {/* Override */}
                          <button
                            onClick={() => handleOpenOverride(r)}
                            className="px-2.5 py-1 rounded border border-slate-300 hover:bg-slate-100 text-slate-700 text-xs font-medium cursor-pointer"
                          >
                            Override
                          </button>
                        </td>
                      </tr>

                      {/* Expandable PR Lines Sub-table */}
                      {isExpanded && (
                        <tr className="bg-slate-50/80">
                          <td colSpan={12} className="px-6 py-3 border-t border-b border-slate-200">
                            <div className="text-xs font-semibold text-slate-600 mb-2">
                              Constituent Purchase Requisition Lines ({r.lines.length}):
                            </div>
                            <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
                              <table className="w-full text-left text-xs">
                                <thead className="bg-slate-100 text-slate-600 font-semibold">
                                  <tr>
                                    <th className="px-4 py-2">PR Line</th>
                                    <th className="px-4 py-2">Requester</th>
                                    <th className="px-4 py-2">Dept</th>
                                    <th className="px-4 py-2 text-right">Quantity</th>
                                    <th className="px-4 py-2">Need-by Date</th>
                                    <th className="px-4 py-2">Urgency</th>
                                    <th className="px-4 py-2">Created At</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 text-slate-600">
                                  {r.lines.map((ln, idx) => (
                                    <tr key={idx} className="hover:bg-slate-50">
                                      <td className="px-4 py-2 font-mono font-medium text-slate-900">
                                        {ln.pr_no} / line {ln.pr_line}
                                      </td>
                                      <td className="px-4 py-2">{ln.requester}</td>
                                      <td className="px-4 py-2">{ln.department}</td>
                                      <td className="px-4 py-2 text-right font-semibold">
                                        {ln.quantity} {ln.uom}
                                      </td>
                                      <td className="px-4 py-2">{ln.need_by_date}</td>
                                      <td className="px-4 py-2">
                                        <span
                                          className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                                            ln.urgency === 'Emergency'
                                              ? 'bg-rose-100 text-rose-800'
                                              : 'bg-slate-100 text-slate-700'
                                          }`}
                                        >
                                          {ln.urgency}
                                        </span>
                                      </td>
                                      <td className="px-4 py-2 text-slate-400">{ln.created_at}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* "Why" Row Detail Drawer */}
      {activeDrawer && (
        <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40 backdrop-blur-xs transition-opacity">
          <div className="w-full max-w-xl bg-white h-full shadow-2xl flex flex-col overflow-y-auto">
            {/* Drawer Header */}
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between sticky top-0 bg-white z-10">
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  Decision Rationale: {activeDrawer.group_id}
                </h3>
                <p className="text-xs text-slate-500">
                  Policy Version: {activeDrawer.policy_version} | Clause: {activeDrawer.clause}
                </p>
              </div>
              <button
                onClick={() => setActiveDrawer(null)}
                className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Drawer Content */}
            <div className="p-6 space-y-6 text-xs text-slate-700">
              {/* Clause & Reason Box */}
              <div className="p-4 bg-sky-50 border border-sky-200 rounded-xl space-y-2">
                <span className="text-[11px] font-bold text-sky-900 uppercase tracking-wider block">
                  Applicable Policy Clause
                </span>
                <p className="text-sm font-semibold text-slate-900">Clause {activeDrawer.clause}</p>
                <p className="text-xs text-slate-700 leading-relaxed">{activeDrawer.reason}</p>
              </div>

              {/* Contract Utilization Bar (if applicable) */}
              {activeDrawer.contract_info && (
                <div className="p-4 bg-white border border-slate-200 rounded-xl space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-900">
                      Contract {activeDrawer.contract_info.contract_id}
                    </span>
                    <span className="font-semibold text-slate-600">
                      {activeDrawer.contract_info.ceiling_used_pct}% Ceil. Used
                    </span>
                  </div>
                  {/* Progress bar */}
                  <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                    <div
                      className={`h-2.5 rounded-full ${
                        activeDrawer.contract_info.ceiling_used_pct > 90
                          ? 'bg-rose-500'
                          : activeDrawer.contract_info.ceiling_used_pct > 75
                          ? 'bg-amber-500'
                          : 'bg-emerald-500'
                      }`}
                      style={{ width: `${Math.min(activeDrawer.contract_info.ceiling_used_pct, 100)}%` }}
                    ></div>
                  </div>
                  <div className="flex justify-between text-[11px] text-slate-500">
                    <span>
                      Consumed: ₹{activeDrawer.contract_info.consumed_value.toLocaleString('en-IN')}
                    </span>
                    <span>
                      Ceiling: ₹{activeDrawer.contract_info.value_ceiling.toLocaleString('en-IN')}
                    </span>
                  </div>
                </div>
              )}

              {/* Clubbing Explanation */}
              <div className="p-4 bg-white border border-slate-200 rounded-xl space-y-2">
                <span className="text-[11px] font-bold text-slate-800 uppercase tracking-wider block">
                  Line Clubbing Details (Policy Section 2)
                </span>
                <p className="text-xs text-slate-600 leading-relaxed">
                  Clubbed {activeDrawer.lines.length} lines for item{' '}
                  <span className="font-semibold">{activeDrawer.item_code}</span> at plant{' '}
                  <span className="font-semibold">{activeDrawer.plant}</span>. Line creation times
                  fell within the 14-day creation window and need-by dates within the 7-day tolerance.
                </p>
                <div className="text-slate-900 font-semibold pt-1">
                  Total Requisition Value: ₹
                  {activeDrawer.value_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
              </div>

              {/* Preferred Ranking Breakdown Table */}
              {activeDrawer.preferred_ranking && activeDrawer.preferred_ranking.length > 0 && (
                <div className="p-4 bg-white border border-slate-200 rounded-xl space-y-3">
                  <span className="text-[11px] font-bold text-slate-800 uppercase tracking-wider block">
                    Preferred Supplier Ranking & Score Breakdown
                  </span>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-[11px]">
                      <thead className="bg-slate-50 font-semibold text-slate-600 border-b">
                        <tr>
                          <th className="px-2 py-1.5">Rank</th>
                          <th className="px-2 py-1.5">Supplier</th>
                          <th className="px-2 py-1.5 text-right">Score</th>
                          <th className="px-2 py-1.5 text-right">Ref Price</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {activeDrawer.preferred_ranking.map((s) => (
                          <tr key={s.rank}>
                            <td className="px-2 py-1.5 font-bold">#{s.rank}</td>
                            <td className="px-2 py-1.5">{s.supplier_name}</td>
                            <td className="px-2 py-1.5 text-right font-semibold text-sky-700">
                              {s.total_score}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {s.reference_price ? `₹${s.reference_price.toFixed(2)}` : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Rejected Alternatives */}
              {activeDrawer.rejected_alternatives && (
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
                  <span className="text-[11px] font-bold text-slate-700 uppercase tracking-wider block">
                    Evaluated Alternatives
                  </span>
                  <ul className="list-disc pl-4 space-y-1 text-slate-600">
                    {activeDrawer.rejected_alternatives.map((alt, idx) => (
                      <li key={idx}>{alt}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Drawer Action Bar */}
              <div className="pt-4 border-t border-slate-200 flex justify-end space-x-3">
                <button
                  onClick={() => {
                    handleOpenOverride(activeDrawer);
                    setActiveDrawer(null);
                  }}
                  className="px-4 py-2 rounded-lg border border-slate-300 hover:bg-slate-100 text-slate-700 font-medium text-xs cursor-pointer"
                >
                  Override Decision
                </button>
                <button
                  onClick={() => {
                    handleApproveSingle(activeDrawer.group_id);
                    setActiveDrawer(null);
                  }}
                  className="px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-700 text-white font-medium text-xs shadow-sm cursor-pointer"
                >
                  Approve Recommendation
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Override Modal */}
      {overrideTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-xl shadow-2xl border border-slate-200 max-w-lg w-full p-6 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200">
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  Override Decision: {overrideTarget.group_id}
                </h3>
                <p className="text-xs text-slate-500">
                  Item: {overrideTarget.item_code} | Original Route: {overrideTarget.route}
                </p>
              </div>
              <button
                onClick={() => setOverrideTarget(null)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-700 font-medium mb-1">Route</label>
                <select
                  value={overrideRoute}
                  onChange={(e) => setOverrideRoute(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-900 focus:outline-none"
                >
                  <option value="CONTRACT_PO">CONTRACT_PO</option>
                  <option value="SPOT_PO">SPOT_PO</option>
                  <option value="RFQ">RFQ</option>
                  <option value="RFP">RFP</option>
                  <option value="CAPEX_SOURCING">CAPEX_SOURCING</option>
                  <option value="NEW_ITEM_SOURCING">NEW_ITEM_SOURCING</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-700 font-medium mb-1">Supplier ID</label>
                <input
                  type="text"
                  value={overrideSupplier}
                  onChange={(e) => setOverrideSupplier(e.target.value)}
                  placeholder="e.g. S014"
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-900 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-medium mb-1">Unit Price (INR)</label>
                <input
                  type="number"
                  step="0.01"
                  value={overridePrice}
                  onChange={(e) => setOverridePrice(e.target.value)}
                  placeholder="e.g. 520.00"
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-900 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-medium mb-1">
                  Justification Comment <span className="text-rose-500">*</span>
                </label>
                <textarea
                  rows={3}
                  value={overrideComment}
                  onChange={(e) => setOverrideComment(e.target.value)}
                  placeholder="Required: Provide operational or commercial reason for overriding system policy..."
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-900 focus:outline-none"
                />
              </div>
            </div>

            <div className="pt-3 border-t border-slate-200 flex justify-end space-x-3">
              <button
                onClick={() => setOverrideTarget(null)}
                className="px-4 py-2 rounded-lg border border-slate-300 hover:bg-slate-100 text-slate-700 text-xs font-medium"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveOverride}
                disabled={overrideSubmitting || !overrideComment.trim()}
                className="px-5 py-2 rounded-lg bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white font-medium text-xs shadow-sm cursor-pointer"
              >
                {overrideSubmitting ? 'Saving...' : 'Save & Record Override'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


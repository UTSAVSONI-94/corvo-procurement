import React, { useState, useEffect } from 'react';
import { Award, Calendar, Download, Search, TrendingUp, Layers } from 'lucide-react';
import { fetchPreferredSuppliers, fetchItemsList } from '../api';

export default function PreferredSuppliersView() {
  const [items, setItems] = useState([]);
  const [selectedItem, setSelectedItem] = useState('');
  const [asOfDate, setAsOfDate] = useState('2026-11-01');
  const [rankingData, setRankingData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function loadItems() {
      try {
        const itms = await fetchItemsList();
        setItems(itms);
        if (itms.length > 0) {
          setSelectedItem(itms[0].item_code);
        }
      } catch (err) {
        console.error('Failed to load items', err);
      }
    }
    loadItems();
  }, []);

  const handleQuery = async (itemCodeToQuery, dateToQuery) => {
    const code = itemCodeToQuery || selectedItem;
    const dt = dateToQuery || asOfDate;
    if (!code) return;

    setLoading(true);
    setError(null);
    try {
      const data = await fetchPreferredSuppliers(code, dt);
      setRankingData(data);
    } catch (err) {
      setError(err.message || 'Failed to query preferred suppliers');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedItem) {
      handleQuery(selectedItem, asOfDate);
    }
  }, [selectedItem, asOfDate]);

  const handleExportCsv = () => {
    window.location.href = `/api/export/preferred-suppliers?as_of=${asOfDate}`;
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header and Controls */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900">Preferred Suppliers Ranking</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Policy Section 6: Multi-factor weighted score calculation and reference pricing.
            </p>
          </div>

          {/* Primary Action: Export CSV */}
          <div>
            <button
              onClick={handleExportCsv}
              className="px-5 py-2.5 rounded-lg bg-sky-600 hover:bg-sky-700 text-white font-medium text-xs shadow-sm flex items-center space-x-2 transition-colors cursor-pointer"
            >
              <Download className="w-4 h-4" />
              <span>Export CSV</span>
            </button>
          </div>
        </div>

        {/* Selection Bar */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4 border-t border-slate-100 text-xs">
          <div>
            <label className="block font-medium text-slate-700 mb-1">Select Item Code</label>
            <select
              value={selectedItem}
              onChange={(e) => setSelectedItem(e.target.value)}
              className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-900 focus:outline-none"
            >
              {items.map((it) => (
                <option key={it.item_code} value={it.item_code}>
                  {it.item_code} - {it.description} ({it.category})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block font-medium text-slate-700 mb-1">As-Of Date</label>
            <div className="relative">
              <Calendar className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
              <input
                type="date"
                value={asOfDate}
                onChange={(e) => setAsOfDate(e.target.value)}
                className="w-full pl-9 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-900 focus:outline-none"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Results View */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-slate-800">
              Ranked Suppliers for <span className="text-sky-700 font-mono">{selectedItem}</span>
            </h3>
            <p className="text-xs text-slate-500">
              Evaluated using active policy weights: frequency (0.30), recency (0.25), contract (0.20), on-time (0.15), quality (0.10)
            </p>
          </div>
          {rankingData && (
            <span className="text-xs px-2.5 py-1 bg-slate-100 rounded-full font-medium text-slate-600">
              {rankingData.total_ranked} eligible supplier(s)
            </span>
          )}
        </div>

        {loading ? (
          <div className="p-12 text-center text-slate-400 text-sm">
            <div className="animate-spin w-6 h-6 border-2 border-sky-600 border-t-transparent rounded-full mx-auto mb-2"></div>
            Computing multi-factor ranking scores...
          </div>
        ) : !rankingData || rankingData.suppliers.length === 0 ? (
          <div className="p-12 text-center text-slate-400 text-sm">
            No active preferred suppliers found for {selectedItem} within the 548-day window.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-600 uppercase font-semibold border-b border-slate-200">
                <tr>
                  <th className="px-6 py-3 w-16 text-center">Rank</th>
                  <th className="px-6 py-3">Supplier ID & Name</th>
                  <th className="px-6 py-3 text-right">Reference Price</th>
                  <th className="px-6 py-3 text-right">Total Score</th>
                  <th className="px-6 py-3">Score Breakdown (Component / Contrib.)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 text-slate-700">
                {rankingData.suppliers.map((s) => (
                  <tr key={s.rank} className="hover:bg-slate-50/70">
                    <td className="px-6 py-4 text-center font-bold text-slate-900">
                      <span
                        className={`inline-flex items-center justify-center w-7 h-7 rounded-full text-xs ${
                          s.rank === 1
                            ? 'bg-amber-100 text-amber-900 border border-amber-300'
                            : s.rank === 2
                            ? 'bg-slate-200 text-slate-800'
                            : 'bg-slate-100 text-slate-600'
                        }`}
                      >
                        {s.rank}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="font-semibold text-slate-900">{s.supplier_name}</div>
                      <div className="font-mono text-[11px] text-slate-500">{s.supplier_id}</div>
                    </td>
                    <td className="px-6 py-4 text-right font-medium text-slate-900">
                      {s.reference_price ? (
                        <span>₹{s.reference_price.toFixed(2)}</span>
                      ) : (
                        <span className="text-slate-400 italic">None</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-right font-bold text-sky-700 text-sm">
                      {s.total_score.toFixed(4)}
                    </td>
                    <td className="px-6 py-4">
                      <div className="grid grid-cols-5 gap-2 text-[10px]">
                        {s.breakdown.map((b, idx) => (
                          <div
                            key={idx}
                            className="p-1.5 bg-slate-50 border border-slate-200 rounded text-center"
                          >
                            <span className="text-slate-400 block font-medium uppercase">
                              {b.component.replace('_pct', '').replace('_rating', '')}
                            </span>
                            <span className="font-semibold text-slate-800">
                              {b.contribution.toFixed(3)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}


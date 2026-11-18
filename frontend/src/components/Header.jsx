import React from 'react';
import { ShieldCheck, UserCircle2 } from 'lucide-react';

export default function Header({ role, onRoleChange, activePolicy }) {
  const roles = [
    { id: 'Requester', label: 'Requester' },
    { id: 'Buyer', label: 'Buyer' },
    { id: 'Procurement Admin', label: 'Procurement Admin' },
  ];

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-lg bg-sky-600 flex items-center justify-center text-white font-bold text-lg shadow-sm">
            C
          </div>
          <div>
            <h1 className="text-base font-semibold text-slate-900 leading-tight">Corvo Engineering</h1>
            <p className="text-xs text-slate-500">Autonomous Procurement Engine</p>
          </div>
        </div>

        {/* Center: Active Policy Badge */}
        <div className="flex items-center space-x-2 bg-sky-50 border border-sky-200 text-sky-800 px-3 py-1.5 rounded-full text-xs font-medium">
          <ShieldCheck className="w-4 h-4 text-sky-600" />
          <span>Active Policy:</span>
          <span className="font-semibold underline decoration-sky-400">
            {activePolicy ? activePolicy.version_label : 'v5.0'}
          </span>
          <span className="text-sky-500">
            ({activePolicy ? activePolicy.effective_from : '2026-11-01'})
          </span>
        </div>

        {/* Right: Role Switcher */}
        <div className="flex items-center space-x-2">
          <div className="flex items-center space-x-1.5 text-xs text-slate-500 mr-1">
            <UserCircle2 className="w-4 h-4 text-slate-400" />
            <span>Role:</span>
          </div>
          <div className="inline-flex rounded-lg p-1 bg-slate-100 border border-slate-200">
            {roles.map((r) => {
              const active = role === r.id;
              return (
                <button
                  key={r.id}
                  onClick={() => onRoleChange(r.id)}
                  className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
                    active
                      ? 'bg-white text-slate-900 shadow-sm'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  {r.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </header>
  );
}


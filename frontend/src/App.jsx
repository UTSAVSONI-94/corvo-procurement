import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import ChatView from './views/ChatView';
import BatchesView from './views/BatchesView';
import BuyerWorkspace from './views/BuyerWorkspace';
import PreferredSuppliersView from './views/PreferredSuppliersView';
import PolicyManagementView from './views/PolicyManagementView';
import ContractsView from './views/ContractsView';
import AuditLogView from './views/AuditLogView';
import { fetchActivePolicy } from './api';
import {
  MessageSquare,
  UploadCloud,
  LayoutDashboard,
  Award,
  ShieldCheck,
  FileCheck2,
  History,
} from 'lucide-react';

export default function App() {
  const [role, setRole] = useState('Buyer');
  const [activeTab, setActiveTab] = useState('workspace');
  const [activePolicy, setActivePolicy] = useState(null);

  const loadActivePolicy = async () => {
    try {
      const p = await fetchActivePolicy();
      setActivePolicy(p);
    } catch (err) {
      console.error('Failed to load active policy', err);
    }
  };

  useEffect(() => {
    loadActivePolicy();
  }, []);

  // Sync default tab when role switches
  const handleRoleChange = (newRole) => {
    setRole(newRole);
    if (newRole === 'Requester') {
      setActiveTab('chat');
    } else if (newRole === 'Buyer') {
      setActiveTab('workspace');
    } else if (newRole === 'Procurement Admin') {
      setActiveTab('policy');
    }
  };

  const navItems = [
    { id: 'chat', label: 'Requester Chat', icon: MessageSquare, roles: ['Requester', 'Buyer', 'Procurement Admin'] },
    { id: 'batches', label: 'Batches', icon: UploadCloud, roles: ['Requester', 'Buyer', 'Procurement Admin'] },
    { id: 'workspace', label: 'Buyer Workspace', icon: LayoutDashboard, roles: ['Buyer', 'Procurement Admin'] },
    { id: 'preferred', label: 'Preferred Suppliers', icon: Award, roles: ['Buyer', 'Procurement Admin'] },
    { id: 'contracts', label: 'Contracts', icon: FileCheck2, roles: ['Buyer', 'Procurement Admin'] },
    { id: 'policy', label: 'Policy Management', icon: ShieldCheck, roles: ['Procurement Admin'] },
    { id: 'audit', label: 'Audit Log', icon: History, roles: ['Buyer', 'Procurement Admin'] },
  ];

  const visibleNav = navItems.filter((item) => item.roles.includes(role));

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900">
      {/* Universal Header with Role Switcher & Active Policy Badge */}
      <Header role={role} onRoleChange={handleRoleChange} activePolicy={activePolicy} />

      {/* Navigation Tabs Bar */}
      <nav className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex space-x-1 overflow-x-auto py-2">
          {visibleNav.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`flex items-center space-x-2 px-3.5 py-2 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors cursor-pointer ${
                  isActive
                    ? 'bg-sky-50 text-sky-700 border border-sky-200 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-sky-600' : 'text-slate-400'}`} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      </nav>

      {/* Main View Port */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === 'chat' && <ChatView activePolicy={activePolicy} />}
        {activeTab === 'batches' && (
          <BatchesView onBatchProcessed={() => {}} />
        )}
        {activeTab === 'workspace' && <BuyerWorkspace />}
        {activeTab === 'preferred' && <PreferredSuppliersView />}
        {activeTab === 'contracts' && <ContractsView />}
        {activeTab === 'policy' && (
          <PolicyManagementView onPolicyActivated={loadActivePolicy} />
        )}
        {activeTab === 'audit' && <AuditLogView />}
      </main>
    </div>
  );
}


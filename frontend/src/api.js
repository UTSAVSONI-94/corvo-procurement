/**
 * frontend/src/api.js
 * Centralized API client talking strictly to the FastAPI backend.
 * Zero business logic - pure data fetching and mutation.
 */

const API_BASE = '/api';

export async function fetchActivePolicy() {
  const res = await fetch(`${API_BASE}/policies`);
  if (!res.ok) throw new Error('Failed to fetch policies');
  const policies = await res.json();
  const active = policies.find(p => p.status === 'ACTIVE') || policies[0];
  return active;
}

export async function fetchAllPolicies() {
  const res = await fetch(`${API_BASE}/policies`);
  if (!res.ok) throw new Error('Failed to fetch policies');
  return res.json();
}

export async function fetchPolicyDetail(policyId) {
  const res = await fetch(`${API_BASE}/policies/${policyId}`);
  if (!res.ok) throw new Error(`Failed to fetch policy ${policyId}`);
  return res.json();
}

export async function ingestPolicy(payload) {
  // payload can be FormData or JSON object { instruction, text }
  const isFormData = payload instanceof FormData;
  const res = await fetch(`${API_BASE}/policies/ingest`, {
    method: 'POST',
    body: isFormData ? payload : JSON.stringify(payload),
    headers: isFormData ? undefined : { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Ingestion failed' }));
    throw new Error(err.detail || 'Policy ingestion failed');
  }
  return res.json();
}

export async function approvePolicy(policyId, body = {}) {
  const res = await fetch(`${API_BASE}/policies/${policyId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Approval failed' }));
    throw new Error(err.detail || 'Policy approval failed');
  }
  return res.json();
}

// Chat Intake API
export async function sendChatMessage(message, sessionId = null, refDate = null) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      ref_date: refDate,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Chat error' }));
    throw new Error(err.detail || 'Chat request failed');
  }
  return res.json();
}

export async function getChatSession(sessionId) {
  const res = await fetch(`${API_BASE}/chat/${sessionId}`);
  if (!res.ok) throw new Error('Chat session not found');
  return res.json();
}

// Batch & Requirements API
export async function processBatch(file = null) {
  let body = null;
  let headers = undefined;
  if (file) {
    body = new FormData();
    body.append('file', file);
  }
  const res = await fetch(`${API_BASE}/process-batch`, {
    method: 'POST',
    body,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Batch processing failed' }));
    throw new Error(err.detail || 'Batch processing failed');
  }
  return res.json();
}

export async function uploadPrBatch(file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/pr/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Upload validation failed' }));
    throw new Error(err.detail || 'Upload validation failed');
  }
  return res.json();
}

export async function fetchRequirements() {
  const res = await fetch(`${API_BASE}/requirements`);
  if (!res.ok) throw new Error('Failed to fetch requirements');
  return res.json();
}

export async function approveRequirements(groupIds, actor = 'Buyer') {
  const res = await fetch(`${API_BASE}/requirements/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ group_ids: groupIds, approved_by: actor }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Approval failed' }));
    throw new Error(err.detail || 'Approval failed');
  }
  return res.json();
}

export async function overrideRequirement(groupId, data) {
  const res = await fetch(`${API_BASE}/requirements/${groupId}/override`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Override failed' }));
    throw new Error(err.detail || 'Override failed');
  }
  return res.json();
}

// Contracts API
export async function fetchContracts(params = {}) {
  const query = new URLSearchParams();
  if (params.search) query.set('search', params.search);
  if (params.status) query.set('status', params.status);
  if (params.source) query.set('source', params.source);
  if (params.supplier_id) query.set('supplier_id', params.supplier_id);
  const res = await fetch(`${API_BASE}/contracts?${query.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch contracts');
  return res.json();
}

export async function extractContractPdf(file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/contracts/extract`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'PDF extraction failed' }));
    throw new Error(err.detail || 'PDF extraction failed');
  }
  return res.json();
}

export async function confirmContract(payload) {
  const res = await fetch(`${API_BASE}/contracts/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Contract confirmation failed' }));
    throw new Error(err.detail || 'Contract confirmation failed');
  }
  return res.json();
}

export async function manualContract(payload) {
  const res = await fetch(`${API_BASE}/contracts/manual`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Manual contract save failed' }));
    throw new Error(err.detail || 'Manual contract save failed');
  }
  return res.json();
}

// Preferred Suppliers API
export async function fetchPreferredSuppliers(itemCode, asOfDate = null) {
  const query = new URLSearchParams();
  if (itemCode) query.set('item_code', itemCode);
  if (asOfDate) query.set('as_of', asOfDate);
  const res = await fetch(`${API_BASE}/preferred-suppliers?${query.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch preferred suppliers');
  return res.json();
}

export async function fetchItemsList() {
  const res = await fetch(`${API_BASE}/items`);
  if (!res.ok) throw new Error('Failed to fetch items');
  return res.json();
}

// Audit Log API
export async function fetchAuditLogs(params = {}) {
  const query = new URLSearchParams();
  if (params.entity) query.set('entity', params.entity);
  if (params.action) query.set('action', params.action);
  if (params.who) query.set('who', params.who);
  const res = await fetch(`${API_BASE}/audit-log?${query.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch audit log');
  return res.json();
}


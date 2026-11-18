import React, { useState, useEffect, useRef } from 'react';
import { Send, Bot, User, CheckCircle2, AlertCircle, Sparkles, Clock, MapPin, Layers } from 'lucide-react';
import { sendChatMessage } from '../api';

export default function ChatView({ activePolicy }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: "Hello! I am your Corvo Procurement Assistant. Tell me what you need to procure (e.g. 'Need 200 nitrile gloves for Chakan by next Friday'). I'll help slot-fill requirements and prepare your Requisition.",
    },
  ]);
  const [input, setInput] = useState('');
  const [sessionId, setSessionId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeDraft, setActiveDraft] = useState(null);
  const [statusMessage, setStatusMessage] = useState(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleSend = async (textToSend) => {
    const text = (textToSend || input).trim();
    if (!text || loading) return;

    const userMsg = { role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await sendChatMessage(text, sessionId);
      if (res.session_id) setSessionId(res.session_id);

      const botMsg = { role: 'assistant', content: res.reply };
      setMessages((prev) => [...prev, botMsg]);

      if (res.draft) {
        setActiveDraft(res.draft);
        if (res.draft.created_pr_no) {
          setStatusMessage({
            pr_no: res.draft.created_pr_no,
            status: `Requisition ${res.draft.created_pr_no} created and evaluated under active policy.`,
          });
        }
      }

      if (res.created_pr_no) {
        setStatusMessage({
          pr_no: res.created_pr_no,
          status: res.status_oneliner || `Requisition ${res.created_pr_no} created and routed for policy evaluation.`,
        });
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Error: ${err.message}. Please try again.` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleChipClick = (val) => {
    handleSend(val);
  };

  const handleConfirmPR = () => {
    handleSend('confirm');
  };

  return (
    <div className="max-w-4xl mx-auto h-[calc(100vh-10rem)] flex flex-col bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
      {/* Top Banner */}
      <div className="px-6 py-3.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></div>
          <span className="text-sm font-semibold text-slate-800">Requester Intake Assistant</span>
        </div>
        <div className="text-xs text-slate-500">
          Ref Date: <span className="font-mono font-medium text-slate-700">2026-11-18</span>
        </div>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.map((m, idx) => {
          const isUser = m.role === 'user';
          return (
            <div
              key={idx}
              className={`flex items-start space-x-3 ${isUser ? 'flex-row-reverse space-x-reverse' : ''}`}
            >
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-sm ${
                  isUser
                    ? 'bg-slate-900 text-white'
                    : 'bg-sky-100 text-sky-700 border border-sky-200'
                }`}
              >
                {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
              </div>
              <div
                className={`max-w-lg rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  isUser
                    ? 'bg-slate-900 text-white rounded-br-none shadow-sm'
                    : 'bg-slate-50 text-slate-800 border border-slate-200 rounded-bl-none'
                }`}
              >
                <div className="whitespace-pre-wrap">{m.content}</div>
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="flex items-center space-x-3 text-slate-400 text-sm">
            <div className="w-8 h-8 rounded-full bg-sky-50 flex items-center justify-center text-sky-600 animate-pulse">
              <Bot className="w-4 h-4" />
            </div>
            <div className="flex space-x-1">
              <div className="w-2 h-2 rounded-full bg-slate-300 animate-bounce"></div>
              <div className="w-2 h-2 rounded-full bg-slate-300 animate-bounce [animation-delay:0.2s]"></div>
              <div className="w-2 h-2 rounded-full bg-slate-300 animate-bounce [animation-delay:0.4s]"></div>
            </div>
          </div>
        )}

        {/* PR Confirmation Card if draft is ready */}
        {activeDraft && (activeDraft.status === 'READY_FOR_CONFIRMATION' || (activeDraft.item_code && activeDraft.quantity && activeDraft.plant && activeDraft.need_by_date && activeDraft.status !== 'CONFIRMED')) && (
          <div className="my-4 p-5 bg-sky-50 border-2 border-sky-300 rounded-xl shadow-sm">
            <div className="flex items-center justify-between pb-3 border-b border-sky-200">
              <div className="flex items-center space-x-2">
                <CheckCircle2 className="w-5 h-5 text-sky-600" />
                <h4 className="text-sm font-bold text-sky-950 uppercase tracking-wide">
                  Requisition Ready for Confirmation
                </h4>
              </div>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-sky-200 text-sky-800 font-semibold">
                Draft #{activeDraft.draft_id}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 py-3 text-xs">
              <div>
                <span className="text-slate-500">Item:</span>{' '}
                <span className="font-semibold text-slate-900">
                  {activeDraft.item_code || 'NEW Item'} ({activeDraft.description})
                </span>
              </div>
              <div>
                <span className="text-slate-500">Plant:</span>{' '}
                <span className="font-semibold text-slate-900">{activeDraft.plant}</span>
              </div>
              <div>
                <span className="text-slate-500">Quantity:</span>{' '}
                <span className="font-semibold text-slate-900">
                  {activeDraft.quantity} {activeDraft.uom}
                </span>
              </div>
              <div>
                <span className="text-slate-500">Need-by Date:</span>{' '}
                <span className="font-semibold text-slate-900">{activeDraft.need_by_date}</span>
              </div>
              <div>
                <span className="text-slate-500">Urgency:</span>{' '}
                <span
                  className={`font-semibold ${
                    activeDraft.urgency === 'Emergency' ? 'text-rose-600' : 'text-slate-900'
                  }`}
                >
                  {activeDraft.urgency}
                </span>
              </div>
              {activeDraft.estimated_unit_price && (
                <div>
                  <span className="text-slate-500">Est. Unit Price:</span>{' '}
                  <span className="font-semibold text-slate-900">
                    ₹{activeDraft.estimated_unit_price}
                  </span>
                </div>
              )}
            </div>

            <div className="mt-2 pt-3 border-t border-sky-200 flex items-center justify-end">
              <button
                onClick={handleConfirmPR}
                className="w-full sm:w-auto px-5 py-2.5 rounded-lg bg-sky-600 hover:bg-sky-700 text-white font-medium text-xs shadow-sm flex items-center justify-center space-x-2 transition-colors cursor-pointer"
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>Confirm PR</span>
              </button>
            </div>
          </div>
        )}

        {/* Success Card when PR is finalized */}
        {statusMessage && (
          <div className="my-3 p-4 bg-emerald-50 border border-emerald-300 rounded-xl text-emerald-900 text-xs">
            <div className="flex items-center space-x-2 font-bold mb-1">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>Purchase Requisition Finalized: {statusMessage.pr_no}</span>
            </div>
            <div className="text-emerald-700">{statusMessage.status}</div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Quick Reply Chips */}
      <div className="px-6 py-2 bg-slate-50 border-t border-slate-200 flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-400 flex items-center space-x-1">
          <Sparkles className="w-3 h-3 text-amber-500" />
          <span>Quick replies:</span>
        </span>
        <button
          onClick={() => handleChipClick('Chakan (CHK1)')}
          className="text-xs bg-white border border-slate-200 hover:border-sky-500 hover:text-sky-600 text-slate-700 px-2.5 py-1 rounded-full transition-colors"
        >
          📍 Chakan (CHK1)
        </button>
        <button
          onClick={() => handleChipClick('Pune (PUN1)')}
          className="text-xs bg-white border border-slate-200 hover:border-sky-500 hover:text-sky-600 text-slate-700 px-2.5 py-1 rounded-full transition-colors"
        >
          📍 Pune (PUN1)
        </button>
        <button
          onClick={() => handleChipClick('Urgency: Normal')}
          className="text-xs bg-white border border-slate-200 hover:border-sky-500 hover:text-sky-600 text-slate-700 px-2.5 py-1 rounded-full transition-colors"
        >
          ⏱️ Normal
        </button>
        <button
          onClick={() => handleChipClick('Urgency: Emergency')}
          className="text-xs bg-white border border-slate-200 hover:border-rose-500 hover:text-rose-600 text-slate-700 px-2.5 py-1 rounded-full transition-colors"
        >
          🚨 Emergency
        </button>
        <button
          onClick={() => handleChipClick('Confirm')}
          className="text-xs bg-sky-100 border border-sky-300 hover:bg-sky-200 text-sky-800 font-semibold px-2.5 py-1 rounded-full transition-colors"
        >
          ✓ Confirm
        </button>
      </div>

      {/* Input Bar */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSend();
        }}
        className="p-4 bg-white border-t border-slate-200 flex items-center space-x-3"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Describe your requisition or answer assistant questions..."
          className="flex-1 px-4 py-2.5 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 focus:bg-white transition-all text-slate-900"
        />
        <button
          type="submit"
          disabled={!input.trim() || loading}
          className="px-5 py-2.5 rounded-lg bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white font-medium text-sm flex items-center space-x-2 transition-colors cursor-pointer shadow-sm"
        >
          <span>Send</span>
          <Send className="w-4 h-4" />
        </button>
      </form>
    </div>
  );
}


import React, { useState, useEffect } from 'react';
import { apiRequest } from '../api';
import { ArrowLeft, Edit2, Trash2, Send, Phone, Calendar, Check, Copy, Download, FileText, Mic } from 'lucide-react';
import { translations } from '../i18n';

export default function CustomerDetail({
  customerId,
  language = 'en',
  onBack,
  onNavigateToAddTx,
  onNavigateToQuickAdd,
  onRefreshDashboard
}) {
  const t = translations[language];
  const [customer, setCustomer] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);
  const [reminderData, setReminderData] = useState(null);
  const [showEditNamePhone, setShowEditNamePhone] = useState(false);
  const [editName, setEditName] = useState('');
  const [editPhone, setEditPhone] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const [editTxData, setEditTxData] = useState(null); // { id, amount, note } for inline edit
  const [copied, setCopied] = useState(false);
  const [reminderError, setReminderError] = useState('');
  const [reminderLang, setReminderLang] = useState(language);
  const [pdfLang, setPdfLang] = useState(language);

  // Undo States
  const [undoTx, setUndoTx] = useState(null);
  const [undoCountdown, setUndoCountdown] = useState(0);

  useEffect(() => {
    fetchCustomerDetails();
  }, [customerId, page]);

  useEffect(() => {
    if (customer && customer.phone) {
      fetchReminderLink();
    }
  }, [reminderLang]);

  useEffect(() => {
    if (undoCountdown <= 0) {
      setUndoTx(null);
      return;
    }
    const timer = setTimeout(() => {
      setUndoCountdown(prev => prev - 1);
    }, 1000);
    return () => clearTimeout(timer);
  }, [undoCountdown]);

  const handleDownloadPDF = async (range) => {
    if (!navigator.onLine) {
      alert("PDF download requires an active internet connection.");
      return;
    }
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${import.meta.env.VITE_API_BASE_URL || ''}/api/customers/${customerId}/export/pdf?range=${range}&lang=${pdfLang}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        }
      );
      if (!response.ok) throw new Error("Download failed");
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${customer?.name || 'customer'}_ledger_${range}_${pdfLang}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (e) {
      alert("Failed to export customer PDF.");
    }
  };

  const fetchReminderLink = async () => {
    setReminderError('');
    try {
      const reminderRes = await apiRequest(`/api/customers/${customerId}/reminder-link?lang=${reminderLang}`);
      setReminderData(reminderRes.data);
    } catch (e) {
      console.warn("Failed to generate reminder link", e);
      setReminderError(e.message || t.invalid_pin);
      setReminderData(null);
    }
  };

  const fetchCustomerDetails = async () => {
    setLoading(true);
    setError('');
    setReminderError('');
    setReminderData(null);
    try {
      const { data } = await apiRequest(`/api/customers/${customerId}?page=${page}&size=10`);
      setCustomer(data);
      setEditName(data.name);
      setEditPhone(data.phone || '');

      // Load reminder link if phone number exists
      if (data.phone) {
        await fetchReminderLink();
      } else {
        setReminderData(null);
        setReminderError(t.phone_label);
      }
    } catch (err) {
      setError(err.message || 'Failed to load customer details.');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateCustomer = async (e) => {
    e.preventDefault();
    if (!editName.trim()) return;

    try {
      await apiRequest(`/api/customers/${customerId}`, {
        method: 'PUT',
        body: JSON.stringify({ name: editName.trim(), phone: editPhone.trim() || null })
      });
      setShowEditNamePhone(false);
      fetchCustomerDetails();
      onRefreshDashboard();
    } catch (err) {
      setError(err.message || 'Failed to update customer info.');
    }
  };

  const handleDeleteCustomer = async (force = false) => {
    setDeleteError('');
    try {
      await apiRequest(`/api/customers/${customerId}?force=${force}`, {
        method: 'DELETE'
      });
      onRefreshDashboard();
      onBack();
    } catch (err) {
      if (err.message && err.message.error === 'outstanding_balance') {
        setDeleteConfirm(true); // Open double-confirm dialogue
      } else {
        setDeleteError(err.message?.message || err.message || 'Failed to delete customer.');
      }
    }
  };

  const handleEditTx = (tx) => {
    setEditTxData({
      id: tx.id,
      amount: (tx.amount / 100).toString(),
      note: tx.note || ''
    });
  };

  const handleSaveTxUpdate = async (e) => {
    e.preventDefault();
    const paiseAmount = Math.round(parseFloat(editTxData.amount) * 100);
    if (isNaN(paiseAmount) || paiseAmount <= 0) return;

    try {
      await apiRequest(`/api/transactions/${editTxData.id}`, {
        method: 'PUT',
        body: JSON.stringify({ amount: paiseAmount, note: editTxData.note })
      });
      setEditTxData(null);
      fetchCustomerDetails();
      onRefreshDashboard();
    } catch (err) {
      setError(err.message || 'Failed to update transaction.');
    }
  };

  const handleDeleteTx = async (txId) => {
    if (!window.confirm("Are you sure you want to delete this transaction entry? This will change the balance.")) return;
    try {
      const { data } = await apiRequest(`/api/transactions/${txId}`, {
        method: 'DELETE'
      });
      if (data.deleted_transaction) {
        setUndoTx(data.deleted_transaction);
        setUndoCountdown(5);
      }
      fetchCustomerDetails();
      onRefreshDashboard();
    } catch (err) {
      setError(err.message || 'Failed to delete transaction.');
    }
  };

  const handleUndo = async () => {
    if (!undoTx) return;
    try {
      const undoPayload = {
        ...undoTx,
        idempotency_key: 'undo_' + Date.now() + '_' + Math.random().toString(36).substring(2, 9)
      };
      await apiRequest('/api/transactions', {
        method: 'POST',
        body: JSON.stringify(undoPayload)
      });
      setUndoTx(null);
      setUndoCountdown(0);
      fetchCustomerDetails();
      onRefreshDashboard();
    } catch (e) {
      alert("Failed to restore transaction.");
    }
  };

  const formatRupees = (paise) => {
    const amountRs = paise / 100.0;
    if (amountRs % 1 === 0) return `₹${Math.floor(amountRs)}`;
    return `₹${amountRs.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
  };

  const formatDate = (dateStr) => {
    const d = new Date(dateStr);
    const day = String(d.getDate()).padStart(2, '0');
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const year = d.getFullYear();
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    return `${day}-${month}-${year} ${hours}:${minutes}`;
  };

  const handleCopySMS = () => {
    if (reminderData) {
      navigator.clipboard.writeText(reminderData.sms_text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (loading && !customer) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] p-6 text-center">
        <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mb-3"></div>
        <p className="text-gray-500 font-medium">Loading customer ledger...</p>
      </div>
    );
  }

  if (error && !customer) {
    return (
      <div className="p-6 text-center max-w-md mx-auto space-y-4">
        <div className="bg-red-50 text-red-600 p-4 rounded-2xl border border-red-100 text-sm font-medium">
          {error}
        </div>
        <button onClick={onBack} className="btn-tactile bg-white border px-6 py-2.5 rounded-xl font-semibold">
          Go Back
        </button>
      </div>
    );
  }

  const isDebtor = customer.balance > 0;
  const isCreditor = customer.balance < 0;
  const absBalance = Math.abs(customer.balance);

  return (
    <div className="max-w-md mx-auto p-4 space-y-6 pb-32">
      {/* Header Navigation */}
      <div className="flex justify-between items-center">
        <button
          onClick={onBack}
          className="w-10 h-10 bg-white border border-gray-200 rounded-xl flex items-center justify-center text-gray-600 hover:bg-gray-50 btn-tactile shadow-sm"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex gap-2">
          <button
            onClick={() => setShowEditNamePhone(true)}
            className="w-10 h-10 bg-white border border-gray-200 rounded-xl flex items-center justify-center text-indigo-600 hover:bg-indigo-50 btn-tactile shadow-sm"
            title="Edit Details"
          >
            <Edit2 className="w-4 h-4" />
          </button>
          <button
            onClick={() => handleDeleteCustomer(false)}
            className="w-10 h-10 bg-red-50 border border-red-100 rounded-xl flex items-center justify-center text-red-600 hover:bg-red-100 btn-tactile shadow-sm"
            title={t.delete_customer}
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Customer Info Card */}
      {!showEditNamePhone ? (
        <div className="text-center space-y-1">
          <h2 className="text-2xl font-extrabold text-gray-800">{customer.name}</h2>
          {customer.phone ? (
            <a href={`tel:${customer.phone}`} className="text-sm font-semibold text-indigo-600 flex items-center justify-center gap-1 hover:underline">
              <Phone className="w-3.5 h-3.5" /> {customer.phone}
            </a>
          ) : (
            <p className="text-xs text-gray-400 italic">No phone number</p>
          )}
        </div>
      ) : (
        <form onSubmit={handleUpdateCustomer} className="bg-white rounded-3xl p-4 border border-gray-200 shadow-sm space-y-4">
          <h3 className="font-bold text-gray-800 text-sm">Edit Details</h3>
          <div className="space-y-3">
            <input
              type="text"
              placeholder="Customer Name"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              className="w-full input-ledger text-sm py-2 px-3"
            />
            <input
              type="tel"
              placeholder={t.phone_label}
              value={editPhone}
              onChange={(e) => setEditPhone(e.target.value)}
              className="w-full input-ledger text-sm py-2 px-3"
            />
          </div>
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={() => setShowEditNamePhone(false)}
              className="px-4 py-2 bg-gray-100 rounded-xl text-xs font-semibold text-gray-600 hover:bg-gray-200 btn-tactile"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-indigo-600 rounded-xl text-xs font-semibold text-white hover:bg-indigo-700 btn-tactile"
            >
              Save Changes
            </button>
          </div>
        </form>
      )}

      {/* Double Confirm Customer Deletion */}
      {deleteConfirm && (
        <div className="bg-red-50 border border-red-200 rounded-3xl p-5 text-center space-y-4 animate-fadeIn">
          <h3 className="font-bold text-red-800 text-lg">Warning: Pending Balance</h3>
          <p className="text-sm text-red-700">
            This customer has an outstanding balance of <strong>{formatRupees(customer.balance)}</strong>. Deleting will permanently remove all transaction history and write off this balance.
          </p>
          <div className="flex gap-3 justify-center">
            <button
              onClick={() => setDeleteConfirm(false)}
              className="px-5 py-2.5 bg-white border border-red-200 text-red-700 rounded-xl font-semibold text-sm hover:bg-red-100 btn-tactile"
            >
              Go Back
            </button>
            <button
              onClick={() => handleDeleteCustomer(true)}
              className="px-5 py-2.5 bg-red-600 text-white rounded-xl font-semibold text-sm hover:bg-red-700 btn-tactile"
            >
              Delete Anyway
            </button>
          </div>
        </div>
      )}

      {deleteError && (
        <div className="bg-red-50 text-red-600 p-3 rounded-xl border border-red-100 text-center text-xs font-semibold">
          {deleteError}
        </div>
      )}

      {/* Balance Indicator Display */}
      <div className={`rounded-3xl p-6 text-center border shadow-sm ${
        isDebtor
          ? 'bg-red-50/50 border-red-100 text-ledger-credit'
          : isCreditor
          ? 'bg-green-50/50 border-green-100 text-ledger-payment'
          : 'bg-gray-50 border-gray-150 text-gray-500'
      }`}>
        <span className="text-[10px] uppercase font-bold tracking-widest text-gray-400 block mb-1">
          {isDebtor ? 'Outstanding Credit' : isCreditor ? 'Customer Advance' : 'Account Settled'}
        </span>
        <span className="text-4xl font-extrabold block">
          {formatRupees(absBalance)}
        </span>
      </div>

      {/* Quick Action Buttons */}
      <div className="space-y-3">
        <button
          onClick={() => onNavigateToQuickAdd && customer ? onNavigateToQuickAdd(customer) : null}
          className="w-full py-3.5 bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-700 hover:to-indigo-600 text-white font-extrabold rounded-2xl shadow-md shadow-indigo-600/20 flex items-center justify-center gap-2 btn-tactile text-sm"
        >
          <Mic className="w-5 h-5 text-indigo-200" />
          <span>{t.speak_tx} ({customer?.name})</span>
        </button>

        <div className="grid grid-cols-2 gap-3">
          <button
            onClick={() => onNavigateToAddTx('credit')}
            className="py-3.5 bg-red-600 hover:bg-red-700 text-white font-bold rounded-2xl shadow-md shadow-red-600/10 flex flex-col items-center justify-center gap-0.5 btn-tactile text-base"
          >
            <span className="text-[11px] uppercase tracking-wider font-semibold opacity-80">{t.given_credit}</span>
            <span>{t.add_credit}</span>
          </button>
          <button
            onClick={() => onNavigateToAddTx('payment')}
            className="py-3.5 bg-green-600 hover:bg-green-700 text-white font-bold rounded-2xl shadow-md shadow-green-600/10 flex flex-col items-center justify-center gap-0.5 btn-tactile text-base"
          >
            <span className="text-[11px] uppercase tracking-wider font-semibold opacity-80">{t.got_payment}</span>
            <span>{t.add_payment}</span>
          </button>
        </div>
      </div>

      {/* Reminder Deep Links */}
      <div className="bg-white rounded-3xl p-5 border border-gray-150 shadow-sm space-y-4">
        <div className="flex justify-between items-center border-b border-gray-100 pb-3 mb-2">
          <h4 className="font-bold text-gray-800 text-sm flex items-center gap-1.5">
            <Send className="w-4 h-4 text-indigo-500" /> Settle Reminder
          </h4>
          <div className="flex gap-1 bg-gray-100 p-0.5 rounded-lg border border-gray-200">
            <button
              type="button"
              onClick={() => setReminderLang('en')}
              className={`px-1.5 py-0.5 rounded text-[9px] font-extrabold tracking-wider uppercase transition-all ${
                reminderLang === 'en' ? 'bg-white text-indigo-600 shadow-sm' : 'text-gray-500 hover:text-gray-800'
              }`}
            >
              EN
            </button>
            <button
              type="button"
              onClick={() => setReminderLang('te')}
              className={`px-1.5 py-0.5 rounded text-[9px] font-extrabold tracking-wider uppercase transition-all ${
                reminderLang === 'te' ? 'bg-white text-indigo-600 shadow-sm' : 'text-gray-500 hover:text-gray-800'
              }`}
            >
              తెలుగు
            </button>
            <button
              type="button"
              onClick={() => setReminderLang('hi')}
              className={`px-1.5 py-0.5 rounded text-[9px] font-extrabold tracking-wider uppercase transition-all ${
                reminderLang === 'hi' ? 'bg-white text-indigo-600 shadow-sm' : 'text-gray-500 hover:text-gray-800'
              }`}
            >
              हिंदी
            </button>
          </div>
        </div>
        {reminderData ? (
          <>
            <div className="flex gap-2">
              <a
                href={reminderData.wa_link}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-1 bg-green-500 hover:bg-green-600 text-white py-3 px-4 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 btn-tactile shadow-sm shadow-green-500/10"
              >
                Send WhatsApp
              </a>
              <button
                onClick={handleCopySMS}
                className="bg-gray-100 hover:bg-gray-200 text-gray-700 py-3 px-4 rounded-xl font-semibold text-sm flex items-center justify-center gap-1.5 btn-tactile"
              >
                {copied ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
                {copied ? 'Copied' : 'Copy SMS'}
              </button>
            </div>
            <div className="bg-gray-50 rounded-xl p-3 border border-gray-100">
              <p className="text-xs text-gray-500 italic font-medium leading-relaxed">
                "{reminderData.sms_text}"
              </p>
            </div>
          </>
        ) : (
          <div className="space-y-3">
            <button
              disabled
              className="w-full bg-gray-200 text-gray-400 py-3 px-4 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 cursor-not-allowed"
            >
              Send WhatsApp
            </button>
            <p className="text-xs text-amber-600 font-semibold text-center bg-amber-50 border border-amber-100 p-2.5 rounded-xl">
              {!customer?.phone ? "Add a phone number to send a reminder" : (reminderError || "Add a valid phone number to send a reminder")}
            </p>
          </div>
        )}
      </div>

      {/* Download PDF Reports */}
      <div className="bg-white rounded-3xl p-5 border border-gray-150 shadow-sm space-y-4">
        <div className="flex justify-between items-center border-b border-gray-100 pb-3">
          <h4 className="font-bold text-gray-800 text-sm flex items-center gap-1.5">
            <FileText className="w-4 h-4 text-indigo-500" /> Export PDF Report
          </h4>
          
          <select
            value={pdfLang}
            onChange={(e) => setPdfLang(e.target.value)}
            className="text-xs font-bold bg-gray-50 border border-gray-200 rounded-lg px-2 py-1 text-gray-700 outline-none"
          >
            <option value="en">English</option>
            <option value="te">తెలుగు (Telugu)</option>
            <option value="hi">हिंदी (Hindi)</option>
          </select>
        </div>

        <div className="flex flex-col gap-2.5">
          <button
            type="button"
            onClick={() => handleDownloadPDF('today')}
            className="w-full bg-indigo-50 border border-indigo-100 hover:bg-indigo-100 text-indigo-700 py-3 px-4 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 btn-tactile shadow-sm"
          >
            <Download className="w-4 h-4 text-indigo-600" /> Today's Transactions PDF
          </button>
          <button
            type="button"
            onClick={() => handleDownloadPDF('all')}
            className="w-full bg-indigo-50 border border-indigo-100 hover:bg-indigo-100 text-indigo-700 py-3 px-4 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 btn-tactile shadow-sm"
          >
            <Download className="w-4 h-4 text-indigo-600" /> All-time Transactions PDF
          </button>
        </div>
      </div>

      {/* Edit Transaction Modal / Overlay Form */}
      {editTxData && (
        <div className="fixed inset-0 bg-black/50 flex items-end justify-center z-50 p-4">
          <form onSubmit={handleSaveTxUpdate} className="bg-white rounded-t-3xl md:rounded-3xl p-6 max-w-md w-full shadow-2xl space-y-4 animate-slideUp">
            <h3 className="text-lg font-bold text-gray-800">Correct Entry Mistakes</h3>
            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1">Corrected Amount (₹)</label>
              <input
                type="number"
                step="0.01"
                min="0.01"
                placeholder="Amount in Rupees"
                value={editTxData.amount}
                onChange={(e) => setEditTxData({ ...editTxData, amount: e.target.value })}
                className="w-full input-ledger text-lg font-bold"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1">Corrected Note / Description</label>
              <input
                type="text"
                placeholder="Item details"
                value={editTxData.note}
                onChange={(e) => setEditTxData({ ...editTxData, note: e.target.value })}
                className="w-full input-ledger text-sm"
              />
            </div>
            <div className="flex gap-2 pt-2">
              <button
                type="button"
                onClick={() => setEditTxData(null)}
                className="flex-1 py-3 bg-gray-100 rounded-xl text-sm font-semibold text-gray-600 hover:bg-gray-200 btn-tactile"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="flex-1 py-3 bg-indigo-600 rounded-xl text-sm font-semibold text-white hover:bg-indigo-700 btn-tactile"
              >
                Apply Correction
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Transaction History Section */}
      <div className="space-y-3">
        <h3 className="font-extrabold text-gray-800 text-lg">Transaction History</h3>
        
        {customer.transactions.length === 0 ? (
          <div className="bg-white rounded-3xl p-6 text-center border border-gray-100 text-sm text-gray-400 italic font-medium">
            No entries recorded yet.
          </div>
        ) : (
          <div className="space-y-2">
            {customer.transactions.map((tx) => {
              const isTxCredit = tx.type === 'credit';
              return (
                <div key={tx.id} className="bg-white border border-gray-150 rounded-2xl p-4 flex justify-between items-center shadow-sm select-none">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className={`w-2.5 h-2.5 rounded-full ${isTxCredit ? 'bg-red-500' : 'bg-green-500'}`} />
                      <span className="text-sm font-semibold text-gray-500">
                        {isTxCredit ? 'Credit Given' : 'Payment Got'}
                      </span>
                    </div>
                    {tx.note && <p className="text-sm text-gray-700 font-medium">{tx.note}</p>}
                    <div className="flex items-center gap-1.5 text-[10px] text-gray-400 font-medium">
                      <Calendar className="w-3 h-3" />
                      <span>{formatDate(tx.date)}</span>
                      {tx.edited_at && (
                        <span className="bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded font-bold uppercase text-[8px]">
                          Corrected
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <span className={`text-base font-bold block ${isTxCredit ? 'text-ledger-credit' : 'text-ledger-payment'}`}>
                        {isTxCredit ? '+' : '-'}{formatRupees(tx.amount)}
                      </span>
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <button
                        onClick={() => handleEditTx(tx)}
                        className="p-1.5 hover:bg-gray-100 text-indigo-500 rounded-lg btn-tactile"
                        title="Edit Entry"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => handleDeleteTx(tx.id)}
                        className="p-1.5 hover:bg-red-50 text-red-500 rounded-lg btn-tactile"
                        title="Delete Entry"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}

            {/* Pagination Controls */}
            {customer.pages > 1 && (
              <div className="flex justify-between items-center pt-4">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                  className="px-4 py-2 bg-white border border-gray-200 rounded-xl text-sm font-semibold text-gray-600 disabled:opacity-40 hover:bg-gray-50 btn-tactile"
                >
                  Previous
                </button>
                <span className="text-xs text-gray-500 font-bold">
                  Page {page} of {customer.pages}
                </span>
                <button
                  disabled={page >= customer.pages}
                  onClick={() => setPage(page + 1)}
                  className="px-4 py-2 bg-white border border-gray-200 rounded-xl text-sm font-semibold text-gray-600 disabled:opacity-40 hover:bg-gray-50 btn-tactile"
                >
                  Next
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Undo Delete Transaction Toast */}
      {undoTx && (
        <div className="fixed bottom-6 left-1/2 transform -translate-x-1/2 bg-gray-900 text-white px-5 py-4 rounded-2xl flex items-center justify-between gap-6 shadow-2xl w-[90%] max-w-sm z-50 animate-bounce">
          <span className="text-sm font-semibold">{t.tx_deleted} ({undoCountdown}s)</span>
          <button
            onClick={handleUndo}
            className="text-indigo-400 font-extrabold hover:text-indigo-300 text-sm flex items-center gap-1 active:scale-95 transition-all uppercase tracking-wider"
          >
            {t.undo}
          </button>
        </div>
      )}
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import { apiRequest } from '../api';
import { ArrowLeft, Edit2, Trash2, Send, Phone, Calendar, Check, Copy } from 'lucide-react';

export default function CustomerDetail({ customerId, onBack, onNavigateToAddTx, onRefreshDashboard }) {
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

  useEffect(() => {
    fetchCustomerDetails();
  }, [customerId, page]);

  const fetchCustomerDetails = async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await apiRequest(`/api/customers/${customerId}?page=${page}&size=10`);
      setCustomer(data);
      setEditName(data.name);
      setEditPhone(data.phone || '');

      // Load reminder link if phone number exists
      if (data.phone) {
        try {
          const reminderRes = await apiRequest(`/api/customers/${customerId}/reminder-link`);
          setReminderData(reminderRes.data);
        } catch (e) {
          console.warn("Failed to generate reminder link", e);
        }
      } else {
        setReminderData(null);
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
      await apiRequest(`/api/transactions/${txId}`, {
        method: 'DELETE'
      });
      fetchCustomerDetails();
      onRefreshDashboard();
    } catch (err) {
      setError(err.message || 'Failed to delete transaction.');
    }
  };

  const formatRupees = (paise) => {
    const amountRs = paise / 100.0;
    if (amountRs.is_integer) return `₹${amountRs}`;
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
    <div className="max-w-md mx-auto p-4 space-y-6 pb-24">
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
            title="Delete Customer"
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
              placeholder="Phone Number (Optional)"
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
      <div className="grid grid-cols-2 gap-4">
        <button
          onClick={() => onNavigateToAddTx('credit')}
          className="py-4 bg-red-600 hover:bg-red-700 text-white font-bold rounded-2xl shadow-lg shadow-red-600/10 flex flex-col items-center justify-center gap-1 btn-tactile text-lg"
        >
          <span className="text-xs uppercase tracking-wider font-semibold opacity-80">Given (Credit)</span>
          <span>Add Credit</span>
        </button>
        <button
          onClick={() => onNavigateToAddTx('payment')}
          className="py-4 bg-green-600 hover:bg-green-700 text-white font-bold rounded-2xl shadow-lg shadow-green-600/10 flex flex-col items-center justify-center gap-1 btn-tactile text-lg"
        >
          <span className="text-xs uppercase tracking-wider font-semibold opacity-80">Got (Payment)</span>
          <span>Add Payment</span>
        </button>
      </div>

      {/* Reminder Deep Links */}
      {customer.phone ? (
        reminderData && (
          <div className="bg-white rounded-3xl p-5 border border-gray-150 shadow-sm space-y-4">
            <h4 className="font-bold text-gray-800 text-sm flex items-center gap-1.5">
              <Send className="w-4 h-4 text-indigo-500" /> Settle Reminder
            </h4>
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
          </div>
        )
      ) : (
        <div className="bg-amber-50 border border-amber-200 rounded-3xl p-4 text-center">
          <p className="text-xs text-amber-800 font-semibold leading-relaxed">
            WhatsApp/SMS reminders require a phone number. Edit customer details above to configure.
          </p>
        </div>
      )}

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
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import { apiRequest } from '../api';
import { ArrowLeft, IndianRupee, FileText, Calendar, Plus } from 'lucide-react';

export default function AddTransaction({ customerId, txType, onBack, onTransactionSuccess }) {
  const [customerName, setCustomerName] = useState('');
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [date, setDate] = useState('');
  const [isBackdate, setIsBackdate] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchCustomerName();
    // Default date to current local time formatted for datetime-local input
    const now = new Date();
    const tzOffset = now.getTimezoneOffset() * 60000;
    const localISOTime = new Date(now - tzOffset).toISOString().slice(0, 16);
    setDate(localISOTime);
  }, [customerId]);

  const fetchCustomerName = async () => {
    try {
      const { data } = await apiRequest(`/api/customers/${customerId}`);
      setCustomerName(data.name);
    } catch (e) {
      console.error("Failed to fetch customer name", e);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    const parsedAmount = parseFloat(amount);
    if (isNaN(parsedAmount) || parsedAmount <= 0) {
      setError('Please enter a valid amount greater than zero.');
      return;
    }

    // Convert to paise (round to avoid float issues)
    const paiseAmount = Math.round(parsedAmount * 100);

    setLoading(true);
    try {
      let isoDate = null;
      if (isBackdate && date) {
        // Parse date from local datetime-local value to ISO string
        isoDate = new Date(date).toISOString();
      }

      await apiRequest('/api/transactions', {
        method: 'POST',
        body: JSON.stringify({
          customer_id: customerId,
          type: txType, // "credit" or "payment"
          amount: paiseAmount,
          note: note.trim() || null,
          date: isoDate
        })
      });

      onTransactionSuccess();
    } catch (err) {
      setError(err.message || 'Failed to record transaction.');
    } finally {
      setLoading(false);
    }
  };

  const isCredit = txType === 'credit';

  return (
    <div className="max-w-md mx-auto p-4 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button
          onClick={onBack}
          className="w-10 h-10 bg-white border border-gray-200 rounded-xl flex items-center justify-center text-gray-600 hover:bg-gray-50 btn-tactile shadow-sm"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <h2 className="text-xl font-extrabold text-gray-800">
          {isCredit ? 'Record Credit Given' : 'Record Payment Received'}
        </h2>
      </div>

      {/* Info Banner */}
      <div className={`p-4 rounded-3xl border ${
        isCredit ? 'bg-red-50 border-red-100 text-red-900' : 'bg-green-50 border-green-100 text-green-900'
      }`}>
        <p className="text-xs font-semibold">Customer Account</p>
        <p className="text-lg font-bold">{customerName || 'Loading...'}</p>
      </div>

      {/* Form Card */}
      <div className="bg-white rounded-3xl p-6 border border-gray-150 shadow-sm">
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Big Amount Input */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1">
              <IndianRupee className="w-4 h-4 text-gray-400" /> Amount in Rupees (₹)
            </label>
            <div className="relative">
              <input
                type="number"
                step="0.01"
                min="0.01"
                placeholder="0.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                disabled={loading}
                className="w-full input-ledger text-3xl font-extrabold py-4 text-center pr-8"
                autoFocus
                required
              />
            </div>
          </div>

          {/* Optional Note */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1">
              <FileText className="w-4 h-4 text-gray-400" /> Note / Items description (Optional)
            </label>
            <input
              type="text"
              placeholder="e.g. Rice, Dal, Soap or Cash Payment"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              disabled={loading}
              className="w-full input-ledger text-base"
              maxLength={100}
            />
          </div>

          {/* Backdate Checkbox */}
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="backdate-toggle"
              checked={isBackdate}
              onChange={(e) => setIsBackdate(e.target.checked)}
              className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
            />
            <label htmlFor="backdate-toggle" className="text-sm font-bold text-gray-700 cursor-pointer select-none">
              Backdate Transaction (Log for past date)
            </label>
          </div>

          {/* Date Selector (If Backdated) */}
          {isBackdate && (
            <div className="animate-fadeIn">
              <label className="block text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1">
                <Calendar className="w-4 h-4 text-gray-400" /> Transaction Date & Time
              </label>
              <input
                type="datetime-local"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                disabled={loading}
                className="w-full input-ledger text-base"
                required={isBackdate}
              />
            </div>
          )}

          {error && (
            <p className="text-red-500 text-sm font-semibold text-center">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className={`w-full py-4 px-6 rounded-2xl shadow-lg text-white font-bold flex items-center justify-center gap-2 btn-tactile text-lg ${
              isCredit
                ? 'bg-red-600 hover:bg-red-700 shadow-red-600/20'
                : 'bg-green-600 hover:bg-green-700 shadow-green-600/20'
            }`}
          >
            <Plus className="w-5 h-5" />
            {loading
              ? 'Recording...'
              : isCredit
              ? 'Give Credit (+)'
              : 'Receive Payment (-)'}
          </button>
        </form>
      </div>
    </div>
  );
}

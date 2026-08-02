import React, { useState, useEffect } from 'react';
import { apiRequest } from '../api';
import { translations } from '../i18n';
import { ArrowLeft, Search, Plus, Save, IndianRupee, FileText } from 'lucide-react';

export default function QuickAdd({ language, onBack, onTransactionSuccess, offlineQueue, setOfflineQueue }) {
  const t = translations[language];
  const [customers, setCustomers] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Selected Customer and Amount states
  const [selectedCust, setSelectedCust] = useState(null); // { id, name }
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [txType, setTxType] = useState('credit'); // 'credit' | 'payment'
  const [formLoading, setFormLoading] = useState(false);

  useEffect(() => {
    fetchQuickCustomers();
  }, []);

  const fetchQuickCustomers = async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await apiRequest('/api/customers/quick-list');
      setCustomers(data);
    } catch (e) {
      setError('Failed to load quick list.');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveTransaction = async (e) => {
    e.preventDefault();
    setError('');

    const parsedAmount = parseFloat(amount);
    if (isNaN(parsedAmount) || parsedAmount <= 0) {
      setError('Please enter a valid amount.');
      return;
    }

    const paiseAmount = Math.round(parsedAmount * 100);
    const txPayload = {
      customer_id: selectedCust.id,
      type: txType,
      amount: paiseAmount,
      note: note.trim() || null,
      date: new Date().toISOString()
    };

    if (!navigator.onLine) {
      // Offline mode: queue transaction
      const queue = JSON.parse(localStorage.getItem('offline_tx_queue') || '[]');
      queue.push(txPayload);
      localStorage.setItem('offline_tx_queue', JSON.stringify(queue));
      
      // Update memory state
      setOfflineQueue(prev => [...prev, txPayload]);
      onTransactionSuccess();
      return;
    }

    setFormLoading(true);
    try {
      await apiRequest('/api/transactions', {
        method: 'POST',
        body: JSON.stringify(txPayload)
      });
      onTransactionSuccess();
    } catch (err) {
      setError(err.message || 'Failed to record transaction.');
    } finally {
      setFormLoading(false);
    }
  };

  const filteredCustomers = customers.filter(c =>
    c.name.toLowerCase().includes(search.toLowerCase())
  );

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
        <h2 className="text-xl font-extrabold text-gray-800">{t.quick_add}</h2>
      </div>

      {error && (
        <div className="bg-red-50 text-red-600 p-4 rounded-2xl border border-red-100 text-sm font-semibold text-center">
          {error}
        </div>
      )}

      {!selectedCust ? (
        // Step 1: Pick Customer
        <div className="space-y-4">
          <div className="relative">
            <Search className="w-5 h-5 text-gray-400 absolute left-3.5 top-3.5" />
            <input
              type="text"
              placeholder={t.search_placeholder}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-white border border-gray-200 rounded-2xl py-3.5 pl-11 pr-4 text-base focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all shadow-sm"
              autoFocus
            />
          </div>

          <div className="space-y-2">
            {loading ? (
              <div className="text-center py-8">
                <div className="w-6 h-6 border-3 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
                <p className="text-xs text-gray-400 font-medium">Loading customers...</p>
              </div>
            ) : filteredCustomers.length === 0 ? (
              <div className="bg-white rounded-3xl p-6 text-center border border-gray-150 text-sm text-gray-400 italic">
                {t.no_customers}
              </div>
            ) : (
              <div className="bg-white border border-gray-150 rounded-3xl shadow-sm divide-y divide-gray-100 max-h-[60vh] overflow-y-auto">
                {filteredCustomers.map((c) => (
                  <div
                    key={c.id}
                    onClick={() => setSelectedCust({ id: c.id, name: c.name })}
                    className="p-4 flex justify-between items-center hover:bg-gray-50 active:bg-gray-100 transition-colors cursor-pointer select-none"
                  >
                    <span className="font-bold text-gray-800 text-base">{c.name}</span>
                    {c.phone && <span className="text-xs text-gray-400">{c.phone}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      ) : (
        // Step 2: Enter Amount & Details
        <div className="bg-white rounded-3xl p-6 border border-gray-150 shadow-sm space-y-6">
          <div className="bg-indigo-50 border border-indigo-100 p-4 rounded-2xl flex justify-between items-center">
            <div>
              <span className="text-[10px] uppercase font-bold text-indigo-400 block">Customer</span>
              <span className="text-lg font-bold text-indigo-900">{selectedCust.name}</span>
            </div>
            <button
              onClick={() => setSelectedCust(null)}
              className="text-xs font-semibold text-indigo-600 hover:underline"
            >
              Change
            </button>
          </div>

          <form onSubmit={handleSaveTransaction} className="space-y-6">
            {/* Amount */}
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1">
                <IndianRupee className="w-4 h-4 text-gray-400" /> {t.amount_rupees}
              </label>
              <input
                type="number"
                step="0.01"
                min="0.01"
                placeholder="0.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="w-full input-ledger text-3xl font-extrabold py-4 text-center"
                autoFocus
                required
              />
            </div>

            {/* Note */}
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1">
                <FileText className="w-4 h-4 text-gray-400" /> {t.note_placeholder}
              </label>
              <input
                type="text"
                placeholder={t.note_placeholder}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className="w-full input-ledger text-base"
                maxLength={60}
              />
            </div>

            {/* Type Toggle */}
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setTxType('credit')}
                className={`py-3.5 rounded-2xl font-bold text-sm border btn-tactile ${
                  txType === 'credit'
                    ? 'bg-red-600 border-red-600 text-white shadow-md'
                    : 'bg-white border-gray-200 text-red-600 hover:bg-red-50'
                }`}
              >
                {t.add_credit} (+)
              </button>
              <button
                type="button"
                onClick={() => setTxType('payment')}
                className={`py-3.5 rounded-2xl font-bold text-sm border btn-tactile ${
                  txType === 'payment'
                    ? 'bg-green-600 border-green-600 text-white shadow-md'
                    : 'bg-white border-gray-200 text-green-600 hover:bg-green-50'
                }`}
              >
                {t.add_payment} (-)
              </button>
            </div>

            <button
              type="submit"
              disabled={formLoading}
              className={`w-full py-4 px-6 rounded-2xl shadow-lg text-white font-bold flex items-center justify-center gap-2 btn-tactile text-lg ${
                txType === 'credit'
                  ? 'bg-red-600 hover:bg-red-700 shadow-red-600/20'
                  : 'bg-green-600 hover:bg-green-700 shadow-green-600/20'
              }`}
            >
              <Plus className="w-5 h-5" />
              {formLoading
                ? 'Recording...'
                : txType === 'credit'
                ? t.add_credit
                : t.add_payment}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

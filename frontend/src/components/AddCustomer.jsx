import React, { useState } from 'react';
import { apiRequest } from '../api';
import { ArrowLeft, User, Smartphone, Save } from 'lucide-react';

export default function AddCustomer({ onBack, onCustomerAdded }) {
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!name.trim()) {
      setError('Customer name is required.');
      return;
    }

    setLoading(true);
    try {
      const { data } = await apiRequest('/api/customers', {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          phone: phone.trim() || null
        })
      });
      // Redirect directly to their detail view
      onCustomerAdded(data.id);
    } catch (err) {
      setError(err.message || 'Failed to add customer. Please try again.');
    } finally {
      setLoading(false);
    }
  };

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
        <h2 className="text-xl font-extrabold text-gray-800">Add New Customer</h2>
      </div>

      {/* Form */}
      <div className="bg-white rounded-3xl p-6 border border-gray-150 shadow-sm">
        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1">
              <User className="w-4 h-4 text-gray-400" /> Customer Name *
            </label>
            <input
              type="text"
              placeholder="e.g. Rajesh Kumar"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={loading}
              className="w-full input-ledger text-base"
              maxLength={40}
              required
            />
          </div>

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1">
              <Smartphone className="w-4 h-4 text-gray-400" /> Phone Number (Optional)
            </label>
            <input
              type="tel"
              placeholder="10-digit mobile number"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              disabled={loading}
              className="w-full input-ledger text-base"
              maxLength={15}
            />
          </div>

          {error && (
            <p className="text-red-500 text-sm font-semibold text-center">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-bold py-4 px-6 rounded-2xl shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2 btn-tactile text-lg"
          >
            <Save className="w-5 h-5" />
            {loading ? 'Adding Customer...' : 'Save & Open Ledger'}
          </button>
        </form>
      </div>
    </div>
  );
}

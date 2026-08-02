import React, { useState } from 'react';
import { apiRequest } from '../api';
import { ShoppingBag, ArrowRight } from 'lucide-react';

export default function Setup({ onSetupSuccess }) {
  const [shopName, setShopName] = useState('');
  const [pin, setPin] = useState('');
  const [confirmPin, setConfirmPin] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!shopName.trim()) {
      setError('Please enter a shop name.');
      return;
    }
    if (pin.length !== 4 || !/^\d+$/.test(pin)) {
      setError('PIN must be exactly 4 digits.');
      return;
    }
    if (pin !== confirmPin) {
      setError('PINs do not match.');
      return;
    }

    setLoading(true);
    try {
      const { data } = await apiRequest('/api/setup', {
        method: 'POST',
        body: JSON.stringify({
          shop_name: shopName.trim(),
          pin: pin
        })
      });
      localStorage.setItem('token', data.token);
      onSetupSuccess(data.shop_name);
    } catch (err) {
      setError(err.message || 'Setup failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-ledger-bg flex flex-col justify-center p-6 max-w-md mx-auto">
      <div className="bg-white rounded-3xl p-6 shadow-xl border border-gray-100 flex flex-col">
        <div className="flex flex-col items-center text-center mb-8">
          <div className="w-16 h-16 bg-indigo-100 rounded-3xl flex items-center justify-center text-indigo-600 mb-4 shadow-md">
            <ShoppingBag className="w-8 h-8" />
          </div>
          <h1 className="text-2xl font-bold text-ledger-text">First-Time Setup</h1>
          <p className="text-ledger-muted text-sm mt-1">Configure your digital credit ledger book</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">Shop Name</label>
            <input
              type="text"
              placeholder="e.g. Balaji Kirana Store"
              value={shopName}
              onChange={(e) => setShopName(e.target.value)}
              disabled={loading}
              className="w-full input-ledger text-base"
              maxLength={40}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">4-Digit PIN</label>
              <input
                type="password"
                pattern="[0-9]*"
                inputMode="numeric"
                placeholder="••••"
                value={pin}
                onChange={(e) => setPin(e.target.value.slice(0, 4))}
                disabled={loading}
                className="w-full input-ledger text-center text-xl tracking-widest"
              />
            </div>
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">Confirm PIN</label>
              <input
                type="password"
                pattern="[0-9]*"
                inputMode="numeric"
                placeholder="••••"
                value={confirmPin}
                onChange={(e) => setConfirmPin(e.target.value.slice(0, 4))}
                disabled={loading}
                className="w-full input-ledger text-center text-xl tracking-widest"
              />
            </div>
          </div>

          {error && (
            <p className="text-red-500 text-sm font-semibold text-center">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-bold py-4 px-6 rounded-2xl shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2 btn-tactile text-lg"
          >
            {loading ? 'Configuring...' : 'Start Using App'}
            {!loading && <ArrowRight className="w-5 h-5" />}
          </button>
        </form>
      </div>
    </div>
  );
}

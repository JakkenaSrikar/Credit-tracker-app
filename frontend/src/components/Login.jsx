import React, { useState, useEffect } from 'react';
import { apiRequest } from '../api';
import { Lock, ShoppingBag } from 'lucide-react';

export default function Login({ onLoginSuccess }) {
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Auto-submit when pin reaches 4 digits
  useEffect(() => {
    if (pin.length === 4) {
      handleLogin(pin);
    }
  }, [pin]);

  const handleLogin = async (enteredPin) => {
    setLoading(true);
    setError('');
    try {
      const { data } = await apiRequest('/api/login', {
        method: 'POST',
        body: JSON.stringify({ pin: enteredPin }),
      });
      localStorage.setItem('token', data.token);
      onLoginSuccess(data.shop_name);
    } catch (err) {
      setError(err.message || 'Login failed. Please try again.');
      setPin(''); // Reset pin on error
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (num) => {
    if (pin.length < 4 && !loading) {
      setPin(prev => prev + num);
    }
  };

  const handleBackspace = () => {
    if (pin.length > 0 && !loading) {
      setPin(prev => prev.slice(0, -1));
    }
  };

  const handleClear = () => {
    if (!loading) setPin('');
  };

  return (
    <div className="min-h-screen bg-ledger-bg flex flex-col justify-between p-6 max-w-md mx-auto">
      {/* Top Header */}
      <div className="flex flex-col items-center mt-12 text-center">
        <div className="w-16 h-16 bg-indigo-100 rounded-3xl flex items-center justify-center text-indigo-600 mb-4 shadow-md">
          <ShoppingBag className="w-8 h-8" />
        </div>
        <h1 className="text-2xl font-bold text-ledger-text">Udhara Tracker</h1>
        <p className="text-ledger-muted text-sm mt-1">Enter PIN to open ledger book</p>
      </div>

      {/* PIN Dots Display */}
      <div className="my-8 flex flex-col items-center">
        <div className="flex gap-6 justify-center mb-4">
          {[0, 1, 2, 3].map((index) => (
            <div
              key={index}
              className={`w-4 h-4 rounded-full border-2 border-indigo-300 transition-all duration-150 ${
                pin.length > index ? 'bg-indigo-600 scale-110 border-indigo-600' : 'bg-transparent'
              }`}
            />
          ))}
        </div>
        
        {/* Error / Loading Messages */}
        <div className="h-6 text-center">
          {error && <p className="text-red-500 text-sm font-semibold">{error}</p>}
          {loading && <p className="text-indigo-600 text-sm font-semibold animate-pulse">Checking PIN...</p>}
        </div>
      </div>

      {/* Big Numpad */}
      <div className="mb-8">
        <div className="grid grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((num) => (
            <button
              key={num}
              type="button"
              onClick={() => handleKeyPress(num.toString())}
              disabled={loading}
              className="h-16 rounded-2xl bg-white border border-gray-200 text-2xl font-bold text-gray-800 shadow-sm flex items-center justify-center btn-tactile hover:bg-gray-50 active:bg-gray-100"
            >
              {num}
            </button>
          ))}
          <button
            type="button"
            onClick={handleClear}
            disabled={loading}
            className="h-16 rounded-2xl bg-gray-100 text-lg font-semibold text-gray-600 flex items-center justify-center btn-tactile hover:bg-gray-200 active:bg-gray-300"
          >
            Clear
          </button>
          <button
            type="button"
            onClick={() => handleKeyPress('0')}
            disabled={loading}
            className="h-16 rounded-2xl bg-white border border-gray-200 text-2xl font-bold text-gray-800 shadow-sm flex items-center justify-center btn-tactile hover:bg-gray-50 active:bg-gray-100"
          >
            0
          </button>
          <button
            type="button"
            onClick={handleBackspace}
            disabled={loading}
            className="h-16 rounded-2xl bg-gray-100 text-lg font-semibold text-gray-600 flex items-center justify-center btn-tactile hover:bg-gray-200 active:bg-gray-300"
          >
            ⌫
          </button>
        </div>
      </div>

      {/* Footer lock icon */}
      <div className="flex items-center justify-center text-ledger-muted text-xs gap-1.5 mb-4">
        <Lock className="w-3.5 h-3.5" />
        <span>Secure offline ledger storage</span>
      </div>
    </div>
  );
}

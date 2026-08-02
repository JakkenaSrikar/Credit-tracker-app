import React, { useState, useEffect } from 'react';
import { apiRequest } from '../api';
import { Lock, ShoppingBag, ArrowRight, HelpCircle } from 'lucide-react';
import { translations } from '../i18n';

export default function Login({ language = 'en', onLoginSuccess, onNavigateToSignup, onNavigateToReset }) {
  const t = translations[language];
  const [stores, setStores] = useState([]);
  const [selectedStoreId, setSelectedStoreId] = useState('');
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState(1); // 1: Select Store, 2: Enter PIN

  useEffect(() => {
    fetchStores();
  }, []);

  const fetchStores = async () => {
    try {
      const { data } = await apiRequest('/api/stores/list');
      setStores(data);
      if (data.length > 0) {
        setSelectedStoreId(data[0].id.toString());
      }
    } catch (e) {
      setError('Failed to load store list.');
    }
  };

  // Auto-submit when PIN reaches 4 digits
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
        body: JSON.stringify({
          store_id: parseInt(selectedStoreId),
          pin: enteredPin
        }),
      });
      localStorage.setItem('token', data.token);
      onLoginSuccess(data.store_name, data.role, data.language, data.store_id, data.user_id);
    } catch (err) {
      setError(err.message || 'Login failed. Please try again.');
      setPin(''); // Reset PIN on error
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
      <div className="flex flex-col items-center mt-10 text-center">
        <div className="w-16 h-16 bg-indigo-100 rounded-3xl flex items-center justify-center text-indigo-600 mb-4 shadow-md">
          <ShoppingBag className="w-8 h-8" />
        </div>
        <h1 className="text-2xl font-black text-ledger-text">{t.title}</h1>
        <p className="text-ledger-muted text-sm mt-1">
          {step === 1 ? t.select_store : t.login_title}
        </p>
      </div>

      {step === 1 ? (
        // Step 1: Select Store
        <div className="my-auto space-y-6">
          <div className="bg-white rounded-3xl p-6 border border-gray-150 shadow-sm space-y-4">
            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1.5">{t.select_store}</label>
              <select
                value={selectedStoreId}
                onChange={(e) => setSelectedStoreId(e.target.value)}
                className="w-full input-ledger text-base py-3 px-4"
              >
                {stores.length === 0 ? (
                  <option value="">No stores registered</option>
                ) : (
                  stores.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))
                )}
              </select>
            </div>

            {error && <p className="text-red-500 text-sm font-semibold text-center">{error}</p>}

            <button
              onClick={() => {
                if (selectedStoreId) setStep(2);
              }}
              disabled={stores.length === 0}
              className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 text-white font-bold py-4 px-6 rounded-2xl shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2 btn-tactile text-base"
            >
              Continue <ArrowRight className="w-4 h-4" />
            </button>
          </div>

          <div className="text-center">
            <button
              onClick={onNavigateToSignup}
              className="text-sm font-bold text-indigo-600 hover:underline"
            >
              + Register New Shop / Store
            </button>
          </div>
        </div>
      ) : (
        // Step 2: Enter PIN
        <div className="flex-1 flex flex-col justify-between my-4">
          {/* PIN Dots */}
          <div className="my-4 flex flex-col items-center">
            <div className="flex gap-1 justify-center items-center mb-1 text-xs text-indigo-600 font-semibold">
              <span className="font-extrabold text-gray-700">
                {stores.find(s => s.id.toString() === selectedStoreId)?.name}
              </span>
              <button
                onClick={() => {
                  setStep(1);
                  setPin('');
                }}
                className="ml-2 text-indigo-500 hover:underline"
              >
                (change)
              </button>
            </div>

            <div className="flex gap-6 justify-center my-4">
              {[0, 1, 2, 3].map((index) => (
                <div
                  key={index}
                  className={`w-4 h-4 rounded-full border-2 border-indigo-300 transition-all duration-150 ${
                    pin.length > index ? 'bg-indigo-600 scale-110 border-indigo-600' : 'bg-transparent'
                  }`}
                />
              ))}
            </div>

            <div className="h-6 text-center">
              {error && <p className="text-red-500 text-sm font-semibold">{error}</p>}
              {loading && <p className="text-indigo-600 text-sm font-semibold animate-pulse">{t.checking_pin}</p>}
            </div>
          </div>

          {/* Keypad */}
          <div className="mb-4">
            <div className="grid grid-cols-3 gap-3">
              {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((num) => (
                <button
                  key={num}
                  type="button"
                  onClick={() => handleKeyPress(num.toString())}
                  disabled={loading}
                  className="h-14 rounded-2xl bg-white border border-gray-250 text-2xl font-bold text-gray-800 shadow-sm flex items-center justify-center btn-tactile active:bg-gray-100"
                >
                  {num}
                </button>
              ))}
              <button
                type="button"
                onClick={handleClear}
                disabled={loading}
                className="h-14 rounded-2xl bg-gray-100 text-sm font-bold text-gray-600 flex items-center justify-center btn-tactile active:bg-gray-200"
              >
                Clear
              </button>
              <button
                type="button"
                onClick={() => handleKeyPress('0')}
                disabled={loading}
                className="h-14 rounded-2xl bg-white border border-gray-250 text-2xl font-bold text-gray-800 shadow-sm flex items-center justify-center btn-tactile active:bg-gray-100"
              >
                0
              </button>
              <button
                type="button"
                onClick={handleBackspace}
                disabled={loading}
                className="h-14 rounded-2xl bg-gray-100 text-sm font-bold text-gray-600 flex items-center justify-center btn-tactile active:bg-gray-200"
              >
                ⌫
              </button>
            </div>
          </div>

          <div className="text-center flex justify-center gap-6 text-xs font-bold text-indigo-600">
            <button onClick={onNavigateToReset} className="hover:underline flex items-center gap-1">
              <HelpCircle className="w-3.5 h-3.5" /> {t.forgot_pin}
            </button>
          </div>
        </div>
      )}

      {/* Footer lock icon */}
      <div className="flex items-center justify-center text-ledger-muted text-xs gap-1.5 mt-auto mb-2">
        <Lock className="w-3.5 h-3.5" />
        <span>Secure multi-tenant ledger storage</span>
      </div>
    </div>
  );
}

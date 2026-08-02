import React, { useState } from 'react';
import { apiRequest } from '../api';
import { translations } from '../i18n';
import { ShoppingBag, ArrowRight, HelpCircle, Key, ArrowLeft } from 'lucide-react';

export default function Setup({ language = 'en', onSetupSuccess, onBack }) {
  const t = translations[language];
  const [storeName, setStoreName] = useState('');
  const [ownerName, setOwnerName] = useState('');
  const [pin, setPin] = useState('');
  const [confirmPin, setConfirmPin] = useState('');
  
  // Recovery
  const [recoveryQuestion, setRecoveryQuestion] = useState('');
  const [recoveryAnswer, setRecoveryAnswer] = useState('');
  
  const [selLanguage, setSelLanguage] = useState(language);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!storeName.trim() || !ownerName.trim() || !pin.trim()) {
      setError('All fields are required.');
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
    if (!recoveryQuestion.trim() || !recoveryAnswer.trim()) {
      setError('Please provide a PIN recovery question and answer.');
      return;
    }

    setLoading(true);
    try {
      const { data } = await apiRequest('/api/stores', {
        method: 'POST',
        body: JSON.stringify({
          store_name: storeName.trim(),
          owner_name: ownerName.trim(),
          pin: pin.trim(),
          recovery_question: recoveryQuestion.trim(),
          recovery_answer: recoveryAnswer.trim(),
          language: selLanguage
        })
      });
      localStorage.setItem('token', data.token);
      onSetupSuccess(data.store_name, data.role, data.language, data.store_id, data.user_id);
    } catch (err) {
      setError(err.message || 'Signup failed. Please check store name duplicates.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-ledger-bg flex flex-col justify-center p-6 max-w-md mx-auto">
      <div className="bg-white rounded-3xl p-6 shadow-xl border border-gray-150 flex flex-col">
        {/* Back navigation if there are already stores */}
        <div className="flex justify-between items-center mb-6">
          <button
            onClick={onBack}
            className="w-10 h-10 bg-white border border-gray-200 rounded-xl flex items-center justify-center text-gray-600 hover:bg-gray-50 btn-tactile shadow-sm"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="w-10 h-10 bg-indigo-100 rounded-xl flex items-center justify-center text-indigo-600 shadow-sm">
            <ShoppingBag className="w-5 h-5" />
          </div>
        </div>

        <div className="text-center mb-6">
          <h1 className="text-2xl font-black text-ledger-text">{t.store_signup}</h1>
          <p className="text-ledger-muted text-xs mt-1">Register your store and owner account</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">{t.store_name}</label>
            <input
              type="text"
              placeholder="e.g. Balaji Kirana Store"
              value={storeName}
              onChange={(e) => setStoreName(e.target.value)}
              disabled={loading}
              className="w-full input-ledger text-sm py-2 px-3"
              maxLength={40}
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1">{t.owner_name}</label>
              <input
                type="text"
                placeholder="e.g. Amma"
                value={ownerName}
                onChange={(e) => setOwnerName(e.target.value)}
                disabled={loading}
                className="w-full input-ledger text-sm py-2 px-3"
                maxLength={40}
                required
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1">{t.language}</label>
              <select
                value={selLanguage}
                onChange={(e) => setSelLanguage(e.target.value)}
                disabled={loading}
                className="w-full input-ledger text-sm py-2 px-3"
              >
                <option value="en">English</option>
                <option value="te">తెలుగు</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1">{t.pin}</label>
              <input
                type="password"
                pattern="[0-9]*"
                inputMode="numeric"
                placeholder="••••"
                value={pin}
                onChange={(e) => setPin(e.target.value.slice(0, 4))}
                disabled={loading}
                className="w-full input-ledger text-center text-lg tracking-widest py-2 px-3"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1">{t.confirm_pin}</label>
              <input
                type="password"
                pattern="[0-9]*"
                inputMode="numeric"
                placeholder="••••"
                value={confirmPin}
                onChange={(e) => setConfirmPin(e.target.value.slice(0, 4))}
                disabled={loading}
                className="w-full input-ledger text-center text-lg tracking-widest py-2 px-3"
                required
              />
            </div>
          </div>

          {/* Recovery Flow Configuration */}
          <div className="pt-2 border-t border-gray-100 space-y-3">
            <span className="text-[10px] uppercase font-bold tracking-widest text-gray-400 block mb-1">
              {t.recovery} (Required)
            </span>
            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1 flex items-center gap-1">
                <HelpCircle className="w-3.5 h-3.5 text-gray-400" /> {t.recovery_question}
              </label>
              <input
                type="text"
                placeholder={t.recovery_prompt}
                value={recoveryQuestion}
                onChange={(e) => setRecoveryQuestion(e.target.value)}
                disabled={loading}
                className="w-full input-ledger text-sm py-2 px-3"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1">{t.recovery_answer}</label>
              <input
                type="text"
                placeholder="Secret answer"
                value={recoveryAnswer}
                onChange={(e) => setRecoveryAnswer(e.target.value)}
                disabled={loading}
                className="w-full input-ledger text-sm py-2 px-3"
                required
              />
            </div>
          </div>

          {error && (
            <p className="text-red-500 text-sm font-semibold text-center">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-bold py-4 px-6 rounded-2xl shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2 btn-tactile text-base"
          >
            {loading ? 'Creating Store...' : t.start_app}
            {!loading && <ArrowRight className="w-4 h-4" />}
          </button>
        </form>
      </div>
    </div>
  );
}

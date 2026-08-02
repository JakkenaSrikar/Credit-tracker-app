import React, { useState, useEffect } from 'react';
import { apiRequest } from '../api';
import { translations } from '../i18n';
import { ArrowLeft, HelpCircle, Key, Check } from 'lucide-react';

export default function PinReset({ language, onBack }) {
  const t = translations[language];
  const [stores, setStores] = useState([]);
  const [selectedStoreId, setSelectedStoreId] = useState('');
  const [userName, setUserName] = useState('');
  const [step, setStep] = useState(1); // 1: username request, 2: question verification
  
  const [userId, setUserId] = useState(null);
  const [recoveryQuestion, setRecoveryQuestion] = useState('');
  const [recoveryAnswer, setRecoveryAnswer] = useState('');
  const [newPin, setNewPin] = useState('');
  
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

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

  const handleRequestQuestion = async (e) => {
    e.preventDefault();
    setError('');

    if (!selectedStoreId || !userName.trim()) {
      setError('Please select store and type user name.');
      return;
    }

    setLoading(true);
    try {
      const { data } = await apiRequest('/api/pin-reset/request', {
        method: 'POST',
        body: JSON.stringify({
          store_id: parseInt(selectedStoreId),
          user_name: userName.trim()
        })
      });
      setUserId(data.user_id);
      setRecoveryQuestion(data.recovery_question);
      setStep(2);
    } catch (err) {
      setError(err.message || 'User or recovery question not found.');
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmReset = async (e) => {
    e.preventDefault();
    setError('');

    if (!recoveryAnswer.trim() || !newPin.trim()) {
      setError('Please fill in all fields.');
      return;
    }
    if (newPin.length !== 4 || !/^\d+$/.test(newPin)) {
      setError('PIN must be exactly 4 digits.');
      return;
    }

    setLoading(true);
    try {
      await apiRequest('/api/pin-reset/confirm', {
        method: 'POST',
        body: JSON.stringify({
          store_id: parseInt(selectedStoreId),
          user_id: userId,
          recovery_answer: recoveryAnswer.trim(),
          new_pin: newPin.trim()
        })
      });
      setSuccess(true);
    } catch (err) {
      setError(err.message || 'Incorrect recovery answer or reset failed.');
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen bg-ledger-bg flex flex-col justify-center p-6 max-w-md mx-auto">
        <div className="bg-white rounded-3xl p-6 shadow-xl border border-gray-150 text-center space-y-6">
          <div className="w-16 h-16 bg-green-100 text-green-600 rounded-full flex items-center justify-center mx-auto shadow-md">
            <Check className="w-8 h-8" />
          </div>
          <h2 className="text-xl font-bold text-gray-800">{t.reset_pin} Success</h2>
          <p className="text-sm text-gray-500 font-medium">Your PIN has been updated successfully. You can now log in.</p>
          <button
            onClick={onBack}
            className="w-full py-4 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-2xl shadow-lg shadow-indigo-600/20 btn-tactile text-base"
          >
            {t.login}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-ledger-bg flex flex-col justify-center p-6 max-w-md mx-auto">
      <div className="bg-white rounded-3xl p-6 shadow-xl border border-gray-150 flex flex-col space-y-6">
        {/* Header */}
        <div className="flex items-center gap-4">
          <button
            onClick={onBack}
            className="w-10 h-10 bg-white border border-gray-200 rounded-xl flex items-center justify-center text-gray-600 hover:bg-gray-50 btn-tactile shadow-sm"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h2 className="text-lg font-bold text-gray-800">{t.reset_pin}</h2>
        </div>

        {error && (
          <p className="text-red-500 text-sm font-semibold text-center">{error}</p>
        )}

        {step === 1 ? (
          <form onSubmit={handleRequestQuestion} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1">{t.select_store}</label>
              <select
                value={selectedStoreId}
                onChange={(e) => setSelectedStoreId(e.target.value)}
                className="w-full input-ledger text-sm py-2.5 px-3"
              >
                {stores.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1">{t.username}</label>
              <input
                type="text"
                placeholder="e.g. Owner"
                value={userName}
                onChange={(e) => setUserName(e.target.value)}
                disabled={loading}
                className="w-full input-ledger text-sm py-2.5 px-3"
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-4 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-2xl shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2 btn-tactile text-base"
            >
              Verify Username
            </button>
          </form>
        ) : (
          <form onSubmit={handleConfirmReset} className="space-y-4">
            {/* Question */}
            <div className="bg-indigo-50 border border-indigo-100 rounded-2xl p-4 space-y-1">
              <span className="text-[10px] uppercase font-bold tracking-widest text-indigo-400 block">
                {t.recovery_question}
              </span>
              <p className="text-sm font-semibold text-indigo-900 flex items-center gap-1.5">
                <HelpCircle className="w-4 h-4 text-indigo-500" />
                {recoveryQuestion}
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1">{t.recovery_answer}</label>
              <input
                type="text"
                placeholder="Secret answer"
                value={recoveryAnswer}
                onChange={(e) => setRecoveryAnswer(e.target.value)}
                disabled={loading}
                className="w-full input-ledger text-sm py-2.5 px-3"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1">{t.new_pin} (4 digits)</label>
              <input
                type="password"
                pattern="[0-9]*"
                inputMode="numeric"
                placeholder="••••"
                value={newPin}
                onChange={(e) => setNewPin(e.target.value.slice(0, 4))}
                disabled={loading}
                className="w-full input-ledger text-sm py-2.5 px-3 tracking-widest text-center"
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-4 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-2xl shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2 btn-tactile text-base"
            >
              Reset My PIN
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

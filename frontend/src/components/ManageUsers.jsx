import React, { useState, useEffect } from 'react';
import { apiRequest } from '../api';
import { translations } from '../i18n';
import { ArrowLeft, UserPlus, Trash2, Key, HelpCircle, Save } from 'lucide-react';

export default function ManageUsers({ language, onBack }) {
  const t = translations[language];
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Add User Form States
  const [name, setName] = useState('');
  const [pin, setPin] = useState('');
  const [role, setRole] = useState('staff');
  const [recoveryQuestion, setRecoveryQuestion] = useState('');
  const [recoveryAnswer, setRecoveryAnswer] = useState('');
  const [formLoading, setFormLoading] = useState(false);

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await apiRequest('/api/users');
      setUsers(data);
    } catch (e) {
      setError(e.message || 'Failed to load user list.');
    } finally {
      setLoading(false);
    }
  };

  const handleAddUser = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    if (!name.trim() || !pin.trim()) {
      setError('Name and PIN are required.');
      return;
    }
    if (pin.length !== 4 || !/^\d+$/.test(pin)) {
      setError('PIN must be exactly 4 digits.');
      return;
    }
    if (recoveryQuestion.trim() && !recoveryAnswer.trim()) {
      setError('Please provide an answer for the recovery question.');
      return;
    }

    setFormLoading(true);
    try {
      await apiRequest('/api/users', {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          pin: pin.trim(),
          role,
          recovery_question: recoveryQuestion.trim() || null,
          recovery_answer: recoveryAnswer.trim() || null
        })
      });
      setSuccess('User created successfully!');
      setName('');
      setPin('');
      setRole('staff');
      setRecoveryQuestion('');
      setRecoveryAnswer('');
      fetchUsers();
    } catch (e) {
      setError(e.message || 'Failed to create user.');
    } finally {
      setFormLoading(false);
    }
  };

  const handleDeleteUser = async (userId, userName) => {
    if (!window.confirm(`Are you sure you want to delete staff account '${userName}'?`)) return;
    setError('');
    setSuccess('');
    try {
      await apiRequest(`/api/users/${userId}`, { method: 'DELETE' });
      setSuccess('User deleted successfully.');
      fetchUsers();
    } catch (e) {
      setError(e.message || 'Failed to delete user.');
    }
  };

  return (
    <div className="max-w-md mx-auto p-4 space-y-6 pb-24">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button
          onClick={onBack}
          className="w-10 h-10 bg-white border border-gray-200 rounded-xl flex items-center justify-center text-gray-600 hover:bg-gray-50 btn-tactile shadow-sm"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <h2 className="text-xl font-extrabold text-gray-800">{t.users_title}</h2>
      </div>

      {error && (
        <div className="bg-red-50 text-red-600 p-4 rounded-2xl border border-red-100 text-sm font-semibold text-center">
          {error}
        </div>
      )}

      {success && (
        <div className="bg-green-50 text-green-600 p-4 rounded-2xl border border-green-100 text-sm font-semibold text-center">
          {success}
        </div>
      )}

      {/* Add User Form */}
      <div className="bg-white rounded-3xl p-5 border border-gray-150 shadow-sm space-y-4">
        <h3 className="font-bold text-gray-800 text-sm flex items-center gap-1.5">
          <UserPlus className="w-4 h-4 text-indigo-500" /> {t.add_user}
        </h3>
        <form onSubmit={handleAddUser} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1">{t.username}</label>
              <input
                type="text"
                placeholder="e.g. Nanna"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={formLoading}
                className="w-full input-ledger text-sm py-2 px-3"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1">{t.role}</label>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                disabled={formLoading}
                className="w-full input-ledger text-sm py-2 px-3"
              >
                <option value="staff">{t.staff}</option>
                <option value="owner">{t.owner}</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1">{t.pin} (4 digits)</label>
              <input
                type="password"
                pattern="[0-9]*"
                inputMode="numeric"
                placeholder="••••"
                value={pin}
                onChange={(e) => setPin(e.target.value.slice(0, 4))}
                disabled={formLoading}
                className="w-full input-ledger text-sm py-2 px-3 tracking-widest text-center"
                required
              />
            </div>
          </div>

          <div className="space-y-3 pt-2 border-t border-gray-100">
            <span className="text-[10px] uppercase font-bold tracking-widest text-gray-400 block mb-1">
              {t.recovery} (Optional)
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
                disabled={formLoading}
                className="w-full input-ledger text-sm py-2 px-3"
              />
            </div>
            {recoveryQuestion.trim() && (
              <div>
                <label className="block text-xs font-semibold text-gray-500 mb-1">{t.recovery_answer}</label>
                <input
                  type="text"
                  placeholder="Secret answer"
                  value={recoveryAnswer}
                  onChange={(e) => setRecoveryAnswer(e.target.value)}
                  disabled={formLoading}
                  className="w-full input-ledger text-sm py-2 px-3"
                  required={!!recoveryQuestion.trim()}
                />
              </div>
            )}
          </div>

          <button
            type="submit"
            disabled={formLoading}
            className="w-full py-3.5 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-xl flex items-center justify-center gap-2 btn-tactile text-sm shadow-md"
          >
            <Save className="w-4 h-4" />
            {formLoading ? 'Creating...' : t.add_user}
          </button>
        </form>
      </div>

      {/* Users List */}
      <div className="space-y-3">
        <h3 className="font-extrabold text-gray-800 text-base">{t.users_title}</h3>
        
        {loading ? (
          <div className="text-center py-6">
            <div className="w-6 h-6 border-3 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
            <p className="text-xs text-gray-400 font-medium">Loading user access list...</p>
          </div>
        ) : (
          <div className="bg-white border border-gray-150 rounded-3xl shadow-sm divide-y divide-gray-100 overflow-hidden">
            {users.map((u) => (
              <div key={u.id} className="p-4 flex justify-between items-center">
                <div className="space-y-0.5">
                  <h4 className="font-bold text-gray-800 text-base">{u.name}</h4>
                  <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ${
                    u.role === 'owner' ? 'bg-indigo-100 text-indigo-800' : 'bg-gray-100 text-gray-600'
                  }`}>
                    {u.role === 'owner' ? t.owner : t.staff}
                  </span>
                </div>
                <button
                  onClick={() => handleDeleteUser(u.id, u.name)}
                  className="p-2 hover:bg-red-50 text-red-500 rounded-lg btn-tactile"
                  title={t.delete_user}
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

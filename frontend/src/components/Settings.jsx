import React from 'react';
import { apiRequest } from '../api';
import { translations } from '../i18n';
import { ArrowLeft, Languages, Users, Moon, Type, ShieldAlert } from 'lucide-react';

export default function Settings({
  language,
  setLanguage,
  darkMode,
  setDarkMode,
  largeFont,
  setLargeFont,
  role,
  onBack,
  onNavigate
}) {
  const t = translations[language];

  const handleLanguageChange = async (newLang) => {
    try {
      await apiRequest('/api/stores/settings', {
        method: 'PUT',
        body: JSON.stringify({ language: newLang })
      });
      setLanguage(newLang);
    } catch (e) {
      console.error("Failed to update store language settings", e);
      // Fallback local change if offline
      setLanguage(newLang);
    }
  };

  const toggleDarkMode = () => {
    const nextVal = !darkMode;
    setDarkMode(nextVal);
    localStorage.setItem('darkMode', nextVal ? 'true' : 'false');
    if (nextVal) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  };

  const toggleLargeFont = () => {
    const nextVal = !largeFont;
    setLargeFont(nextVal);
    localStorage.setItem('largeFont', nextVal ? 'true' : 'false');
    if (nextVal) {
      document.documentElement.classList.add('text-lg-mode');
    } else {
      document.documentElement.classList.remove('text-lg-mode');
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
        <h2 className="text-xl font-extrabold text-gray-800">{t.settings}</h2>
      </div>

      <div className="bg-white rounded-3xl p-6 border border-gray-150 shadow-sm space-y-6">
        
        {/* Language Selection */}
        <div className="space-y-3">
          <label className="text-sm font-bold text-gray-700 flex items-center gap-2">
            <Languages className="w-4 h-4 text-indigo-500" /> {t.language}
          </label>
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => handleLanguageChange('en')}
              className={`py-3 rounded-2xl font-bold text-sm border btn-tactile ${
                language === 'en'
                  ? 'bg-indigo-600 border-indigo-600 text-white shadow-md'
                  : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'
              }`}
            >
              English
            </button>
            <button
              onClick={() => handleLanguageChange('te')}
              className={`py-3 rounded-2xl font-bold text-sm border btn-tactile ${
                language === 'te'
                  ? 'bg-indigo-600 border-indigo-600 text-white shadow-md'
                  : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'
              }`}
            >
              తెలుగు (Telugu)
            </button>
          </div>
        </div>

        {/* Display Toggles */}
        <div className="space-y-4 pt-2 border-t border-gray-100">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-indigo-50 rounded-lg flex items-center justify-center text-indigo-500">
                <Moon className="w-4 h-4" />
              </div>
              <span className="text-base font-bold text-gray-700">{t.dark_mode}</span>
            </div>
            <button
              onClick={toggleDarkMode}
              className={`w-12 h-6 rounded-full p-1 transition-colors duration-200 focus:outline-none ${
                darkMode ? 'bg-indigo-600' : 'bg-gray-350'
              }`}
              style={{ backgroundColor: darkMode ? '#4F46E5' : '#D1D5DB' }}
            >
              <div
                className={`w-4 h-4 rounded-full bg-white transition-transform duration-200 ${
                  darkMode ? 'transform translate-x-6' : ''
                }`}
              />
            </button>
          </div>

          <div className="flex justify-between items-center">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-indigo-50 rounded-lg flex items-center justify-center text-indigo-500">
                <Type className="w-4 h-4" />
              </div>
              <span className="text-base font-bold text-gray-700">{t.large_font}</span>
            </div>
            <button
              onClick={toggleLargeFont}
              className={`w-12 h-6 rounded-full p-1 transition-colors duration-200 focus:outline-none ${
                largeFont ? 'bg-indigo-600' : 'bg-gray-350'
              }`}
              style={{ backgroundColor: largeFont ? '#4F46E5' : '#D1D5DB' }}
            >
              <div
                className={`w-4 h-4 rounded-full bg-white transition-transform duration-200 ${
                  largeFont ? 'transform translate-x-6' : ''
                }`}
              />
            </button>
          </div>
        </div>

        {/* Staff Logins Management (Owner-only) */}
        {role === 'owner' && (
          <div className="pt-4 border-t border-gray-100">
            <button
              onClick={() => onNavigate('manage_users')}
              className="w-full bg-white border border-gray-200 hover:bg-gray-50 text-gray-800 font-bold py-4 px-6 rounded-2xl flex items-center justify-center gap-2 btn-tactile text-base shadow-sm"
            >
              <Users className="w-5 h-5 text-indigo-500" />
              {t.users_title}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

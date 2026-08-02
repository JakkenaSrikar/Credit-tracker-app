import React, { useState, useEffect } from 'react';
import { apiRequest } from '../api';
import { Search, UserPlus, ArrowUpDown, Smartphone, Download, Settings as SettingsIcon, Zap, ChevronDown, ChevronUp } from 'lucide-react';
import { translations } from '../i18n';

export default function Dashboard({
  shopName,
  language = 'en',
  onSelectCustomer,
  onNavigate,
  refreshTrigger,
  offlineQueueLength = 0
}) {
  const t = translations[language];
  const [summary, setSummary] = useState(null);
  const [todaySummary, setTodaySummary] = useState(null);
  const [showToday, setShowToday] = useState(false);
  const [customers, setCustomers] = useState([]);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('balance_desc');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [isOfflineMode, setIsOfflineMode] = useState(false);

  useEffect(() => {
    fetchDashboardData();
  }, [search, sort, refreshTrigger]);

  const fetchDashboardData = async () => {
    setLoading(true);
    setError('');
    try {
      const [summaryRes, customersRes] = await Promise.all([
        apiRequest('/api/dashboard/summary'),
        apiRequest(`/api/customers?sort=${sort}${search ? `&search=${encodeURIComponent(search)}` : ''}`)
      ]);
      
      setSummary(summaryRes.data);
      setCustomers(customersRes.data);
      setIsOfflineMode(summaryRes.offline || customersRes.offline);

      // Fetch today's summary only if online
      if (navigator.onLine) {
        const todayRes = await apiRequest('/api/dashboard/today');
        setTodaySummary(todayRes.data);
      }
    } catch (err) {
      setError(err.message || 'Failed to load dashboard data.');
    } finally {
      setLoading(false);
    }
  };

  const handleExportCSV = async () => {
    if (!navigator.onLine) {
      alert("CSV Export requires an active internet connection.");
      return;
    }
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/export/transactions`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (!response.ok) throw new Error("Export failed");
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ledger_export_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (e) {
      alert("Failed to export CSV file.");
    }
  };

  const formatRupees = (paise) => {
    const amountRs = paise / 100.0;
    if (amountRs % 1 === 0) return `₹${intFormat(amountRs)}`;
    return `₹${amountRs.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
  };

  const intFormat = (num) => {
    return Math.floor(num).toString();
  };

  const getBalanceStyle = (balance) => {
    if (balance > 0) return 'text-ledger-credit font-bold';
    if (balance < 0) return 'text-ledger-payment font-bold';
    return 'text-gray-400 font-semibold';
  };

  return (
    <div className="pb-32">
      {/* Offline Banner */}
      {(isOfflineMode || !navigator.onLine) && (
        <div className="bg-amber-500 text-white text-xs font-semibold px-4 py-2.5 text-center flex items-center justify-center gap-1.5 animate-pulse">
          <span>{t.offline_msg}</span>
        </div>
      )}

      {/* Pending Sync Badge */}
      {offlineQueueLength > 0 && (
        <div className="bg-indigo-600 text-white text-xs font-bold px-4 py-2 text-center flex items-center justify-center gap-1">
          <Zap className="w-3.5 h-3.5 fill-white" />
          <span>{offlineQueueLength} {t.offline_pending_sync}</span>
        </div>
      )}

      {/* Summary Section */}
      <div className="bg-white border-b border-gray-200 p-6 shadow-sm">
        <div className="max-w-md mx-auto space-y-4">
          <div className="flex justify-between items-center">
            <h2 className="text-xl font-black text-gray-800">{shopName || 'Kirana Shop'}</h2>
            <div className="flex items-center gap-2">
              <button
                onClick={() => onNavigate('settings')}
                className="w-10 h-10 bg-gray-50 hover:bg-gray-100 text-gray-600 rounded-xl flex items-center justify-center btn-tactile border border-gray-150"
                title={t.settings}
              >
                <SettingsIcon className="w-5 h-5" />
              </button>
              <span className={`text-[10px] uppercase font-bold tracking-wider px-2.5 py-1 rounded-full ${
                isOfflineMode || !navigator.onLine ? 'bg-amber-100 text-amber-800' : 'bg-green-100 text-green-800'
              }`}>
                {isOfflineMode || !navigator.onLine ? 'Offline' : 'Online'}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="bg-red-50 rounded-2xl p-4 border border-red-100/50">
              <span className="text-xs font-bold text-red-600 block mb-1">{t.total_owed}</span>
              <span className="text-2xl font-black text-ledger-credit">
                {summary ? formatRupees(summary.total_outstanding) : '₹0'}
              </span>
            </div>
            <div className="bg-indigo-50 rounded-2xl p-4 border border-indigo-100/50">
              <span className="text-xs font-bold text-indigo-600 block mb-1">{t.total_customers}</span>
              <span className="text-2xl font-black text-indigo-900">
                {summary ? summary.total_customers : '0'}
              </span>
            </div>
          </div>

          {/* Quick actions row */}
          <div className="flex gap-2">
            <button
              onClick={handleExportCSV}
              className="flex-1 bg-gray-50 border border-gray-200 hover:bg-gray-100 text-gray-700 font-bold py-2.5 px-4 rounded-xl flex items-center justify-center gap-2 btn-tactile text-sm shadow-sm"
            >
              <Download className="w-4 h-4 text-indigo-500" />
              {t.export_csv}
            </button>
            <button
              onClick={() => onNavigate('quick_add')}
              className="flex-1 bg-indigo-50 border border-indigo-100 hover:bg-indigo-100 text-indigo-700 font-bold py-2.5 px-4 rounded-xl flex items-center justify-center gap-2 btn-tactile text-sm shadow-sm"
            >
              <Zap className="w-4 h-4 text-indigo-600" />
              {t.quick_add}
            </button>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="max-w-md mx-auto p-4 space-y-4">
        
        {/* Today's Closing Summary (Collapsible) */}
        {todaySummary && (
          <div className="bg-white rounded-3xl border border-gray-150 shadow-sm overflow-hidden">
            <button
              onClick={() => setShowToday(!showToday)}
              className="w-full p-4 flex justify-between items-center font-bold text-gray-800 text-sm hover:bg-gray-50"
            >
              <span className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-green-500 animate-pulse"></span>
                {t.today_summary} ({todaySummary.date})
              </span>
              {showToday ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            {showToday && (
              <div className="p-4 bg-gray-50 border-t border-gray-100 space-y-4 text-xs font-semibold text-gray-600">
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-red-50/50 p-3 rounded-xl border border-red-100/30">
                    <span className="text-[10px] text-red-500 block mb-0.5">{t.total_credit}</span>
                    <span className="text-base font-extrabold text-red-600">
                      {formatRupees(todaySummary.total_credit_given)}
                    </span>
                  </div>
                  <div className="bg-green-50/50 p-3 rounded-xl border border-green-100/30">
                    <span className="text-[10px] text-green-500 block mb-0.5">{t.total_payment}</span>
                    <span className="text-base font-extrabold text-green-600">
                      {formatRupees(todaySummary.total_payments_received)}
                    </span>
                  </div>
                </div>

                {todaySummary.transactions.length === 0 ? (
                  <p className="text-center italic text-gray-400 py-2">No transactions logged today.</p>
                ) : (
                  <div className="divide-y divide-gray-150 max-h-48 overflow-y-auto">
                    {todaySummary.transactions.map((tx) => (
                      <div key={tx.id} className="py-2.5 flex justify-between items-center">
                        <div>
                          <span className="font-bold text-gray-800 block text-xs">{tx.customer_name}</span>
                          {tx.note && <span className="text-[10px] text-gray-400 block font-normal">{tx.note}</span>}
                        </div>
                        <span className={`font-bold ${tx.type === 'credit' ? 'text-red-500' : 'text-green-500'}`}>
                          {tx.type === 'credit' ? '+' : '-'}{formatRupees(tx.amount)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Search Bar & Sort Dropdown */}
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="w-5 h-5 text-gray-400 absolute left-3.5 top-3.5" />
            <input
              type="text"
              placeholder={t.search_placeholder}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-white border border-gray-200 rounded-2xl py-3 pl-11 pr-4 text-base focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all shadow-sm"
            />
          </div>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="bg-white border border-gray-200 rounded-2xl px-3 py-3 text-sm font-bold text-gray-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="balance_desc">{t.debt_sort}</option>
            <option value="balance_asc">{t.settled_sort}</option>
            <option value="name_asc">{t.name_sort}</option>
            <option value="created_desc">{t.created_sort}</option>
          </select>
        </div>

        {error && (
          <div className="bg-red-50 text-red-600 p-4 rounded-2xl border border-red-100 text-sm font-medium text-center">
            {error}
          </div>
        )}

        {/* Customer List */}
        <div className="space-y-2">
          {loading && customers.length === 0 ? (
            <div className="text-center py-12">
              <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
              <p className="text-sm text-gray-500 font-medium">Loading ledger...</p>
            </div>
          ) : customers.length === 0 ? (
            <div className="bg-white border border-gray-100 rounded-3xl p-8 text-center shadow-sm">
              <p className="text-gray-500 font-medium text-base">{t.no_customers}</p>
              <button
                onClick={() => onNavigate('add_customer')}
                className="mt-4 inline-flex items-center gap-1.5 px-5 py-2.5 bg-indigo-50 text-indigo-600 rounded-xl font-bold text-sm hover:bg-indigo-100 btn-tactile"
              >
                <UserPlus className="w-4 h-4" /> {t.add_customer}
              </button>
            </div>
          ) : (
            <div className="bg-white border border-gray-150 rounded-3xl shadow-sm overflow-hidden divide-y divide-gray-100">
              {customers.map((c) => (
                <div
                  key={c.id}
                  onClick={() => onSelectCustomer(c.id)}
                  className="p-4 flex justify-between items-center hover:bg-gray-50 transition-colors cursor-pointer select-none active:bg-gray-100"
                >
                  <div className="space-y-0.5">
                    <h3 className="text-lg font-bold text-gray-800">{c.name}</h3>
                    {c.phone ? (
                      <span className="text-xs text-gray-500 font-medium flex items-center gap-1">
                        <Smartphone className="w-3 h-3 text-gray-400" /> {c.phone}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-400 italic">No phone number</span>
                    )}
                  </div>
                  <div className="text-right">
                    <span className={`text-lg ${getBalanceStyle(c.balance)}`}>
                      {formatRupees(c.balance)}
                    </span>
                    <span className="block text-[10px] uppercase font-bold tracking-wider text-gray-400 mt-0.5">
                      {c.balance > 0 ? t.owes_shop : c.balance < 0 ? t.overpaid : t.settled}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Floating Action Buttons */}
      <div className="fixed bottom-6 right-6 flex flex-col gap-3 z-10">
        <button
          onClick={() => onNavigate('quick_add')}
          className="w-12 h-12 bg-indigo-50 text-indigo-600 rounded-full shadow-lg border border-indigo-100 flex items-center justify-center btn-tactile hover:bg-indigo-100 active:scale-95 transition-all"
          title={t.quick_add}
        >
          <Zap className="w-5 h-5 fill-indigo-600" />
        </button>
        <button
          onClick={() => onNavigate('add_customer')}
          className="w-14 h-14 bg-indigo-600 text-white rounded-full shadow-2xl flex items-center justify-center btn-tactile hover:bg-indigo-700 active:scale-95 transition-all"
          title={t.add_customer}
        >
          <UserPlus className="w-6 h-6" />
        </button>
      </div>
    </div>
  );
}

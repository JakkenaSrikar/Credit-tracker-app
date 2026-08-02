import React, { useState, useEffect } from 'react';
import { apiRequest } from '../api';
import { Search, UserPlus, ArrowUpDown, Smartphone, MessageSquare } from 'lucide-react';

export default function Dashboard({ shopName, onSelectCustomer, onNavigate, refreshTrigger }) {
  const [summary, setSummary] = useState(null);
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
      // Fetch summary and customers list in parallel
      const [summaryRes, customersRes] = await Promise.all([
        apiRequest('/api/dashboard/summary'),
        apiRequest(`/api/customers?sort=${sort}${search ? `&search=${encodeURIComponent(search)}` : ''}`)
      ]);
      
      setSummary(summaryRes.data);
      setCustomers(customersRes.data);
      setIsOfflineMode(summaryRes.offline || customersRes.offline);
    } catch (err) {
      setError(err.message || 'Failed to load dashboard data.');
    } finally {
      setLoading(false);
    }
  };

  const formatRupees = (paise) => {
    const amountRs = paise / 100.0;
    if (amountRs.is_integer) return `₹${amountRs}`;
    return `₹${amountRs.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
  };

  const getBalanceStyle = (balance) => {
    if (balance > 0) return 'text-ledger-credit font-bold';
    if (balance < 0) return 'text-ledger-payment font-bold';
    return 'text-gray-400 font-semibold';
  };

  return (
    <div className="pb-24">
      {/* Offline Banner */}
      {isOfflineMode && (
        <div className="bg-amber-500 text-white text-xs font-semibold px-4 py-2 text-center flex items-center justify-center gap-1.5 animate-pulse">
          <span>Offline Mode — Showing Cached Data</span>
        </div>
      )}

      {/* Summary Section */}
      <div className="bg-white border-b border-gray-200 p-6 shadow-sm">
        <div className="max-w-md mx-auto space-y-4">
          <div className="flex justify-between items-center">
            <h2 className="text-xl font-bold text-gray-800">{shopName || 'Kirana Shop'}</h2>
            <span className="text-xs px-2.5 py-1 bg-green-100 text-green-800 rounded-full font-medium">
              {isOfflineMode ? 'Offline' : 'Online'}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="bg-red-50 rounded-2xl p-4 border border-red-100/50">
              <span className="text-xs font-semibold text-red-600 block mb-1">Total Owed (Outstanding)</span>
              <span className="text-2xl font-extrabold text-ledger-credit">
                {summary ? formatRupees(summary.total_outstanding) : '₹0'}
              </span>
            </div>
            <div className="bg-indigo-50 rounded-2xl p-4 border border-indigo-100/50">
              <span className="text-xs font-semibold text-indigo-600 block mb-1">Total Customers</span>
              <span className="text-2xl font-extrabold text-indigo-900">
                {summary ? summary.total_customers : '0'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="max-w-md mx-auto p-4 space-y-4">
        
        {/* Search Bar & Sort Dropdown */}
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="w-5 h-5 text-gray-400 absolute left-3.5 top-3.5" />
            <input
              type="text"
              placeholder="Search customer name..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-white border border-gray-200 rounded-2xl py-3 pl-11 pr-4 text-base focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all shadow-sm"
            />
          </div>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="bg-white border border-gray-200 rounded-2xl px-3 py-3 text-sm font-semibold text-gray-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="balance_desc">Highest Debt</option>
            <option value="balance_asc">Lowest Debt</option>
            <option value="name_asc">Alphabetical</option>
            <option value="created_desc">Newest First</option>
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
              <p className="text-gray-500 font-medium text-base">No customers found</p>
              <p className="text-gray-400 text-sm mt-1">Try searching for a different name or add a new customer.</p>
              <button
                onClick={() => onNavigate('add_customer')}
                className="mt-4 inline-flex items-center gap-1.5 px-5 py-2.5 bg-indigo-50 text-indigo-600 rounded-xl font-bold text-sm hover:bg-indigo-100 btn-tactile"
              >
                <UserPlus className="w-4 h-4" /> Add Customer
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
                    <span className="block text-[10px] uppercase font-semibold tracking-wider text-gray-400 mt-0.5">
                      {c.balance > 0 ? 'Owes shop' : c.balance < 0 ? 'Overpaid' : 'Settled'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Floating Action Button (FAB) */}
      <button
        onClick={() => onNavigate('add_customer')}
        className="fixed bottom-6 right-6 w-14 h-14 bg-indigo-600 text-white rounded-full shadow-2xl flex items-center justify-center btn-tactile hover:bg-indigo-700 active:scale-95 transition-all z-10"
        title="Add Customer"
      >
        <UserPlus className="w-6 h-6" />
      </button>
    </div>
  );
}

import React, { useState, useEffect, useRef } from 'react';
import { apiRequest } from '../api';
import { translations } from '../i18n';
import { useVoiceRecorder } from '../useVoiceRecorder';
import { 
  ArrowLeft, Search, Plus, Save, IndianRupee, FileText, 
  Mic, Square, X, CheckCircle, AlertCircle, RefreshCw, 
  Edit3, User, Tag, Sparkles, WifiOff
} from 'lucide-react';

export default function QuickAdd({ language, initialCustomer, onBack, onTransactionSuccess, offlineQueue, setOfflineQueue }) {
  const t = translations[language] || translations.en;
  
  // Navigation mode: 'voice' | 'manual'
  const [entryMode, setEntryMode] = useState('voice');

  // Customer List
  const [customers, setCustomers] = useState([]);
  const [loadingCustomers, setLoadingCustomers] = useState(true);
  const [customerSearch, setCustomerSearch] = useState('');

  // Voice State Machine: 'ready' | 'recording' | 'processing' | 'clarify_customer' | 'review' | 'saving' | 'success' | 'error'
  const [voiceState, setVoiceState] = useState('ready');
  const [processingStage, setProcessingStage] = useState(''); // 'transcribing' | 'extracting' | 'matching'
  const [voiceError, setVoiceError] = useState('');

  // Voice Draft Data
  const [transcript, setTranscript] = useState('');
  const [isEditingTranscript, setIsEditingTranscript] = useState(false);
  const [selectedCust, setSelectedCust] = useState(initialCustomer || null); // { id, name, phone }
  const [customerCandidates, setCustomerCandidates] = useState([]);
  const [txType, setTxType] = useState('credit'); // 'credit' | 'payment'
  const [amount, setAmount] = useState('');
  const [itemsList, setItemsList] = useState([]);
  const [note, setNote] = useState('');
  const [savedResult, setSavedResult] = useState(null);

  // Manual Entry States
  const [manualCust, setManualCust] = useState(null);
  const [manualAmount, setManualAmount] = useState('');
  const [manualNote, setManualNote] = useState('');
  const [manualTxType, setManualTxType] = useState('credit');
  const [manualError, setManualError] = useState('');
  const [manualSubmitting, setManualSubmitting] = useState(false);

  // Voice recorder hook
  const { 
    isSupported: isMicSupported, 
    isRecording, 
    duration, 
    error: recorderError, 
    permissionDenied,
    startRecording, 
    stopRecording, 
    cancelRecording 
  } = useVoiceRecorder({ maxDuration: 25 });

  const amountInputRef = useRef(null);

  const generateIdempotencyKey = () => {
    return 'tx_' + Date.now() + '_' + Math.random().toString(36).substring(2, 11);
  };

  useEffect(() => {
    fetchQuickCustomers();
  }, []);

  const fetchQuickCustomers = async () => {
    setLoadingCustomers(true);
    try {
      const { data } = await apiRequest('/api/customers/quick-list');
      setCustomers(data || []);
    } catch (e) {
      console.warn("Could not load quick customer list", e);
    } finally {
      setLoadingCustomers(false);
    }
  };

  // --- VOICE FLOW ACTIONS ---

  const handleStartVoice = async () => {
    setVoiceError('');
    if (!navigator.onLine) {
      setVoiceError(t.voice_offline_notice);
      setEntryMode('manual');
      return;
    }
    await startRecording();
    setVoiceState('recording');
  };

  const handleStopVoice = async () => {
    const audioBlob = await stopRecording();
    if (!audioBlob) {
      setVoiceState('ready');
      return;
    }

    setVoiceState('processing');
    setProcessingStage('transcribing');

    try {
      // 1. Send Audio to /api/voice/transcribe
      const token = localStorage.getItem('token');
      const transcribeRes = await fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/voice/transcribe?language=${language}`, {
        method: 'POST',
        headers: {
          'Content-Type': audioBlob.type || 'audio/webm',
          'Authorization': token ? `Bearer ${token}` : ''
        },
        body: audioBlob
      });

      if (!transcribeRes.ok) {
        const errData = await transcribeRes.json().catch(() => ({}));
        throw new Error(errData.detail || "Transcription failed.");
      }

      const transcribeData = await transcribeRes.json();
      const spokenText = transcribeData.transcript || '';

      if (!spokenText.trim()) {
        throw new Error("Could not detect any speech. Please try speaking again clearly.");
      }

      setTranscript(spokenText);
      await parseSpokenTranscript(spokenText);

    } catch (err) {
      console.error("Voice processing error:", err);
      setVoiceError(err.message || "Failed to process audio.");
      setVoiceState('error');
    }
  };

  const parseSpokenTranscript = async (textToParse) => {
    setProcessingStage('extracting');
    try {
      const { data } = await apiRequest('/api/voice/parse', {
        method: 'POST',
        body: JSON.stringify({
          transcript: textToParse,
          language: language
        })
      });

      const draft = data.draft;
      const custMatch = data.customer_match;

      // Fill in parsed draft details
      if (draft.transaction_type) {
        setTxType(draft.transaction_type);
      } else {
        setTxType('credit'); // default fallback
      }

      if (draft.amount_rupees) {
        setAmount(draft.amount_rupees.toString());
      } else {
        setAmount('');
      }

      setItemsList(draft.items || []);
      setNote(draft.note || '');

      // Customer resolution
      if (custMatch.matched_customer) {
        setSelectedCust(custMatch.matched_customer);
        setCustomerCandidates([]);
        setVoiceState('review');
      } else if (custMatch.candidates && custMatch.candidates.length > 0) {
        setSelectedCust(null);
        setCustomerCandidates(custMatch.candidates);
        setVoiceState('clarify_customer');
      } else {
        setSelectedCust(null);
        setCustomerCandidates([]);
        setVoiceState('review'); // User will pick customer manually on review screen
      }

      // Auto-focus amount if missing
      if (!draft.amount_rupees) {
        setTimeout(() => amountInputRef.current?.focus(), 300);
      }

    } catch (err) {
      console.error("Transcript parsing error:", err);
      setVoiceError(err.message || "Failed to understand transaction.");
      setVoiceState('error');
    }
  };

  const handleCancelVoice = () => {
    cancelRecording();
    setVoiceState('ready');
    setVoiceError('');
  };

  const handleSelectCandidate = (candidate) => {
    setSelectedCust(candidate);
    setVoiceState('review');
  };

  const handleConfirmTransaction = async () => {
    setVoiceError('');

    if (!selectedCust) {
      setVoiceError(t.no_customer_matched);
      return;
    }

    const parsedAmt = parseFloat(amount);
    if (isNaN(parsedAmt) || parsedAmt <= 0) {
      setVoiceError(t.missing_amount);
      amountInputRef.current?.focus();
      return;
    }

    const paise = Math.round(parsedAmt * 100);
    const key = generateIdempotencyKey();

    const txPayload = {
      customer_id: selectedCust.id,
      type: txType,
      amount: paise,
      note: note.trim() || null,
      date: new Date().toISOString(),
      idempotency_key: key
    };

    if (!navigator.onLine) {
      // Save to offline queue
      const queue = JSON.parse(localStorage.getItem('offline_tx_queue') || '[]');
      queue.push(txPayload);
      localStorage.setItem('offline_tx_queue', JSON.stringify(queue));
      setOfflineQueue(prev => [...prev, txPayload]);

      setSavedResult({
        customer_name: selectedCust.name,
        type: txType,
        amount: paise,
        current_balance: null,
        offline: true
      });
      setVoiceState('success');
      onTransactionSuccess();
      return;
    }

    setVoiceState('saving');
    try {
      const { data } = await apiRequest('/api/transactions', {
        method: 'POST',
        body: JSON.stringify(txPayload)
      });

      setSavedResult({
        customer_name: data.customer_name || selectedCust.name,
        type: data.type,
        amount: data.amount,
        current_balance: data.current_balance,
        offline: false
      });
      setVoiceState('success');
      onTransactionSuccess();
    } catch (err) {
      console.error("Save error:", err);
      setVoiceError(err.message || "Failed to record transaction.");
      setVoiceState('review');
    }
  };

  const handleResetForAnother = () => {
    setVoiceState('ready');
    setTranscript('');
    setSelectedCust(null);
    setCustomerCandidates([]);
    setAmount('');
    setItemsList([]);
    setNote('');
    setSavedResult(null);
    setVoiceError('');
  };

  // --- MANUAL ENTRY ACTIONS ---

  const handleManualSave = async (e) => {
    e.preventDefault();
    setManualError('');

    if (!manualCust) {
      setManualError(t.no_customer_matched);
      return;
    }

    const parsedAmt = parseFloat(manualAmount);
    if (isNaN(parsedAmt) || parsedAmt <= 0) {
      setManualError(t.missing_amount);
      return;
    }

    const paise = Math.round(parsedAmt * 100);
    const key = generateIdempotencyKey();

    const txPayload = {
      customer_id: manualCust.id,
      type: manualTxType,
      amount: paise,
      note: manualNote.trim() || null,
      date: new Date().toISOString(),
      idempotency_key: key
    };

    if (!navigator.onLine) {
      const queue = JSON.parse(localStorage.getItem('offline_tx_queue') || '[]');
      queue.push(txPayload);
      localStorage.setItem('offline_tx_queue', JSON.stringify(queue));
      setOfflineQueue(prev => [...prev, txPayload]);

      setSavedResult({
        customer_name: manualCust.name,
        type: manualTxType,
        amount: paise,
        current_balance: null,
        offline: true
      });
      setEntryMode('voice');
      setVoiceState('success');
      onTransactionSuccess();
      return;
    }

    setManualSubmitting(true);
    try {
      const { data } = await apiRequest('/api/transactions', {
        method: 'POST',
        body: JSON.stringify(txPayload)
      });

      setSavedResult({
        customer_name: data.customer_name || manualCust.name,
        type: data.type,
        amount: data.amount,
        current_balance: data.current_balance,
        offline: false
      });
      setEntryMode('voice');
      setVoiceState('success');
      onTransactionSuccess();
    } catch (err) {
      setManualError(err.message || "Failed to save transaction.");
    } finally {
      setManualSubmitting(false);
    }
  };

  const filteredCustomers = customers.filter(c =>
    c.name.toLowerCase().includes(customerSearch.toLowerCase()) ||
    (c.phone && c.phone.includes(customerSearch))
  );

  return (
    <div className="max-w-md mx-auto p-4 space-y-4">
      {/* Top Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="w-10 h-10 bg-white border border-gray-200 rounded-xl flex items-center justify-center text-gray-600 hover:bg-gray-50 btn-tactile shadow-sm"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h2 className="text-xl font-extrabold text-gray-800">{t.quick_add}</h2>
        </div>

        {/* Offline Badge */}
        {!navigator.onLine && (
          <span className="flex items-center gap-1 text-[11px] font-bold text-amber-700 bg-amber-100 px-2.5 py-1 rounded-full">
            <WifiOff className="w-3.5 h-3.5" />
            Offline ({offlineQueue.length})
          </span>
        )}
      </div>

      {/* Tabs: Voice Khata vs Manual Entry */}
      {voiceState !== 'success' && (
        <div className="flex bg-gray-200/80 p-1 rounded-2xl">
          <button
            type="button"
            onClick={() => { setEntryMode('voice'); setVoiceState('ready'); }}
            className={`flex-1 py-2.5 text-xs sm:text-sm font-extrabold rounded-xl transition-all flex items-center justify-center gap-1.5 ${
              entryMode === 'voice' 
                ? 'bg-white text-indigo-700 shadow-sm' 
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <Sparkles className="w-4 h-4 text-indigo-500" />
            {t.voice_entry}
          </button>
          <button
            type="button"
            onClick={() => { setEntryMode('manual'); }}
            className={`flex-1 py-2.5 text-xs sm:text-sm font-extrabold rounded-xl transition-all flex items-center justify-center gap-1.5 ${
              entryMode === 'manual' 
                ? 'bg-white text-indigo-700 shadow-sm' 
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <Edit3 className="w-4 h-4 text-gray-500" />
            {t.manual_entry}
          </button>
        </div>
      )}

      {/* Error Banners */}
      {(voiceError || recorderError) && (
        <div className="bg-red-50 text-red-700 p-3.5 rounded-2xl border border-red-200 text-xs sm:text-sm font-semibold flex items-center gap-2">
          <AlertCircle className="w-5 h-5 flex-shrink-0 text-red-500" />
          <div className="flex-1">{voiceError || recorderError}</div>
        </div>
      )}

      {/* ======================================================== */}
      {/* 1. VOICE KHATA FLOW                                     */}
      {/* ======================================================== */}
      {entryMode === 'voice' && (
        <>
          {/* STATE A: READY */}
          {voiceState === 'ready' && (
            <div className="space-y-6">
              {/* Big Microphone Card */}
              <div className="bg-white rounded-3xl p-6 sm:p-8 border border-gray-150 shadow-sm text-center space-y-5">
                <div className="space-y-1">
                  <span className="text-xs font-bold text-indigo-600 bg-indigo-50 px-3 py-1 rounded-full uppercase tracking-wider">
                    {t.supported_languages_info}
                  </span>
                  <p className="text-xs text-gray-400 font-medium pt-1">
                    {t.voice_example_prompt}
                  </p>
                </div>

                {/* Big Tactile Microphone Button */}
                <div className="flex justify-center py-2">
                  <button
                    onClick={handleStartVoice}
                    className="w-28 h-28 bg-gradient-to-tr from-indigo-600 to-indigo-500 text-white rounded-full flex flex-col items-center justify-center shadow-xl shadow-indigo-600/30 hover:scale-105 active:scale-95 transition-all btn-tactile group"
                  >
                    <Mic className="w-12 h-12 mb-1 group-hover:scale-110 transition-transform" />
                    <span className="text-[11px] font-extrabold tracking-wide uppercase">Speak</span>
                  </button>
                </div>

                <div className="text-center">
                  <h3 className="text-base font-extrabold text-gray-800">{t.speak_tx}</h3>
                  <p className="text-xs text-gray-500 mt-1">Tap microphone & speak in Telugu, Hindi or English</p>
                </div>
              </div>

              {/* Quick Customer Chips */}
              {customers.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between px-1">
                    <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">Recent Customers</span>
                    <span className="text-[11px] text-gray-400">Tap to start entry</span>
                  </div>
                  <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
                    {customers.slice(0, 6).map(c => (
                      <button
                        key={c.id}
                        onClick={() => {
                          setSelectedCust(c);
                          setVoiceState('review');
                        }}
                        className="bg-white border border-gray-200 hover:border-indigo-300 active:bg-indigo-50 text-gray-700 px-3 py-2 rounded-xl text-xs font-bold whitespace-nowrap btn-tactile shadow-xs"
                      >
                        {c.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* STATE B: RECORDING */}
          {voiceState === 'recording' && (
            <div className="bg-white rounded-3xl p-8 border border-red-200 shadow-md text-center space-y-6 animate-pulse">
              <div className="flex justify-center">
                <div className="w-24 h-24 bg-red-600 text-white rounded-full flex items-center justify-center shadow-xl shadow-red-600/30 animate-bounce">
                  <Mic className="w-10 h-10" />
                </div>
              </div>

              <div className="space-y-1">
                <div className="text-2xl font-black text-red-600 font-mono">
                  00:{duration < 10 ? `0${duration}` : duration}
                </div>
                <h3 className="text-lg font-extrabold text-gray-800">{t.listening}</h3>
                <p className="text-xs text-gray-500">Speaking in Telugu / English / Hindi...</p>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  onClick={handleCancelVoice}
                  className="flex-1 py-3.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-2xl font-bold text-sm btn-tactile flex items-center justify-center gap-1.5"
                >
                  <X className="w-4 h-4" />
                  {t.cancel_recording}
                </button>
                <button
                  onClick={handleStopVoice}
                  className="flex-1 py-3.5 bg-red-600 hover:bg-red-700 text-white rounded-2xl font-bold text-sm shadow-md shadow-red-600/20 btn-tactile flex items-center justify-center gap-1.5"
                >
                  <Square className="w-4 h-4 fill-current" />
                  {t.tap_to_stop}
                </button>
              </div>
            </div>
          )}

          {/* STATE C: PROCESSING */}
          {voiceState === 'processing' && (
            <div className="bg-white rounded-3xl p-8 border border-indigo-150 shadow-sm text-center space-y-6">
              <div className="w-16 h-16 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto"></div>
              <div className="space-y-2">
                <h3 className="text-base font-extrabold text-gray-800">
                  {processingStage === 'transcribing' && t.transcribing}
                  {processingStage === 'extracting' && t.extracting}
                  {processingStage === 'matching' && t.matching_customer}
                </h3>
                <p className="text-xs text-gray-400 font-medium">Please wait a few moments...</p>
              </div>
              <button
                onClick={handleCancelVoice}
                className="text-xs font-bold text-gray-500 hover:text-gray-700 underline"
              >
                {t.cancel_recording}
              </button>
            </div>
          )}

          {/* STATE E: CLARIFY CUSTOMER */}
          {voiceState === 'clarify_customer' && (
            <div className="bg-white rounded-3xl p-6 border border-amber-200 shadow-sm space-y-4">
              <div className="flex items-center gap-2 text-amber-700">
                <AlertCircle className="w-5 h-5 flex-shrink-0" />
                <h3 className="text-sm font-extrabold">{t.clarify_customer}</h3>
              </div>
              <p className="text-xs text-gray-500">{t.candidate_customers}</p>

              <div className="space-y-2 max-h-60 overflow-y-auto">
                {customerCandidates.map(c => (
                  <div
                    key={c.id}
                    onClick={() => handleSelectCandidate(c)}
                    className="p-3.5 rounded-2xl border border-gray-200 hover:border-indigo-500 hover:bg-indigo-50 active:bg-indigo-100 cursor-pointer flex justify-between items-center transition-all btn-tactile"
                  >
                    <div>
                      <span className="font-bold text-gray-900 block text-sm">{c.name}</span>
                      {c.phone && <span className="text-xs text-gray-500">{c.phone}</span>}
                    </div>
                    <span className="text-xs font-extrabold text-indigo-600 bg-white px-2.5 py-1 rounded-lg border border-indigo-100">
                      Select
                    </span>
                  </div>
                ))}
              </div>

              <div className="pt-2 flex justify-between items-center text-xs">
                <button
                  onClick={() => { setSelectedCust(null); setVoiceState('review'); }}
                  className="font-bold text-indigo-600 hover:underline"
                >
                  Search all customers manually →
                </button>
                <button
                  onClick={handleCancelVoice}
                  className="font-semibold text-gray-400 hover:text-gray-600"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* STATE D: REVIEW & CONFIRM TRANSACTION */}
          {voiceState === 'review' && (
            <div className="bg-white rounded-3xl p-5 sm:p-6 border border-gray-150 shadow-sm space-y-5">
              {/* Not saved yet banner */}
              <div className="bg-indigo-50/80 border border-indigo-100 p-3 rounded-2xl flex items-center justify-between">
                <div>
                  <span className="text-xs font-black text-indigo-900 block">{t.review_title}</span>
                  <span className="text-[11px] font-semibold text-indigo-600">{t.review_subtitle}</span>
                </div>
                <span className="text-[10px] font-extrabold uppercase bg-amber-400 text-amber-950 px-2 py-0.5 rounded-md shadow-xs">
                  Draft
                </span>
              </div>

              {/* 1. Customer Selector Card */}
              <div className="bg-gray-50 border border-gray-200 p-3.5 rounded-2xl space-y-2">
                <div className="flex justify-between items-center">
                  <span className="text-[11px] uppercase font-bold text-gray-500 flex items-center gap-1">
                    <User className="w-3.5 h-3.5" /> {t.customer_label}
                  </span>
                  {selectedCust && (
                    <button
                      onClick={() => setSelectedCust(null)}
                      className="text-xs font-bold text-indigo-600 hover:underline"
                    >
                      Change
                    </button>
                  )}
                </div>

                {selectedCust ? (
                  <div className="flex justify-between items-center">
                    <div>
                      <span className="text-base font-extrabold text-gray-900">{selectedCust.name}</span>
                      {selectedCust.phone && <span className="text-xs text-gray-400 block">{selectedCust.phone}</span>}
                    </div>
                    <CheckCircle className="w-5 h-5 text-green-500" />
                  </div>
                ) : (
                  <div className="space-y-2 pt-1">
                    <div className="relative">
                      <Search className="w-4 h-4 text-gray-400 absolute left-3 top-3" />
                      <input
                        type="text"
                        placeholder={t.search_placeholder}
                        value={customerSearch}
                        onChange={(e) => setCustomerSearch(e.target.value)}
                        className="w-full bg-white border border-gray-200 rounded-xl py-2 pl-9 pr-3 text-xs focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                      />
                    </div>
                    <div className="max-h-36 overflow-y-auto divide-y divide-gray-100 border border-gray-150 rounded-xl bg-white">
                      {filteredCustomers.length === 0 ? (
                        <div className="p-3 text-center text-xs text-gray-400 italic">{t.no_customers}</div>
                      ) : (
                        filteredCustomers.slice(0, 5).map(c => (
                          <div
                            key={c.id}
                            onClick={() => setSelectedCust(c)}
                            className="p-2.5 flex justify-between items-center hover:bg-gray-50 active:bg-gray-100 cursor-pointer text-xs"
                          >
                            <span className="font-bold text-gray-800">{c.name}</span>
                            {c.phone && <span className="text-gray-400">{c.phone}</span>}
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* 2. Transaction Type Toggle */}
              <div>
                <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">
                  {t.type_label}
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setTxType('credit')}
                    className={`py-3.5 rounded-2xl font-black text-sm border btn-tactile ${
                      txType === 'credit'
                        ? 'bg-red-600 border-red-600 text-white shadow-md'
                        : 'bg-white border-gray-200 text-red-600 hover:bg-red-50'
                    }`}
                  >
                    + {t.add_credit} (అప్పు)
                  </button>
                  <button
                    type="button"
                    onClick={() => setTxType('payment')}
                    className={`py-3.5 rounded-2xl font-black text-sm border btn-tactile ${
                      txType === 'payment'
                        ? 'bg-green-600 border-green-600 text-white shadow-md'
                        : 'bg-white border-gray-200 text-green-600 hover:bg-green-50'
                    }`}
                  >
                    - {t.add_payment} (వసూలు)
                  </button>
                </div>
              </div>

              {/* 3. Amount Field */}
              <div>
                <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1.5 flex items-center justify-between">
                  <span>{t.amount_label}</span>
                  {!amount && <span className="text-amber-600 font-bold text-[11px]">* Required</span>}
                </label>
                <div className="relative">
                  <span className="absolute left-4 top-3.5 text-2xl font-bold text-gray-400">₹</span>
                  <input
                    ref={amountInputRef}
                    type="number"
                    step="0.01"
                    min="0.01"
                    inputMode="decimal"
                    placeholder="0.00"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    className="w-full bg-gray-50 border border-gray-200 rounded-2xl py-3.5 pl-10 pr-4 text-3xl font-extrabold text-center text-gray-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all shadow-inner"
                    required
                  />
                </div>
              </div>

              {/* 4. Items & Notes Description */}
              <div>
                <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                  <Tag className="w-3.5 h-3.5" /> {t.items_label} (Optional)
                </label>
                <input
                  type="text"
                  placeholder="e.g. Rice 2kg, Oil 1pkt"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  className="w-full bg-white border border-gray-200 rounded-xl py-2.5 px-3.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {/* 5. Spoken Transcript Box */}
              {transcript && (
                <div className="bg-gray-50 border border-gray-200 rounded-2xl p-3 space-y-1.5">
                  <div className="flex justify-between items-center text-[11px] text-gray-400 font-bold uppercase">
                    <span>{t.transcript_label}</span>
                    <button
                      type="button"
                      onClick={() => setIsEditingTranscript(!isEditingTranscript)}
                      className="text-indigo-600 hover:underline flex items-center gap-0.5"
                    >
                      <Edit3 className="w-3 h-3" /> {isEditingTranscript ? "Done" : "Edit"}
                    </button>
                  </div>
                  {isEditingTranscript ? (
                    <div className="space-y-2">
                      <textarea
                        value={transcript}
                        onChange={(e) => setTranscript(e.target.value)}
                        className="w-full bg-white border border-gray-200 rounded-xl p-2 text-xs text-gray-800"
                        rows={2}
                      />
                      <button
                        type="button"
                        onClick={() => { setIsEditingTranscript(false); parseSpokenTranscript(transcript); }}
                        className="text-xs bg-indigo-600 text-white px-3 py-1 rounded-lg font-bold"
                      >
                        Re-process Speech
                      </button>
                    </div>
                  ) : (
                    <p className="text-xs text-gray-700 italic">"{transcript}"</p>
                  )}
                </div>
              )}

              {/* Actions */}
              <div className="space-y-2 pt-2">
                <button
                  type="button"
                  onClick={handleConfirmTransaction}
                  className={`w-full py-4 px-6 rounded-2xl shadow-lg text-white font-extrabold flex items-center justify-center gap-2 btn-tactile text-base ${
                    txType === 'credit'
                      ? 'bg-red-600 hover:bg-red-700 shadow-red-600/20'
                      : 'bg-green-600 hover:bg-green-700 shadow-green-600/20'
                  }`}
                >
                  <Save className="w-5 h-5" />
                  {t.confirm_save}
                </button>

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setManualCust(selectedCust);
                      setManualAmount(amount);
                      setManualNote(note);
                      setManualTxType(txType);
                      setEntryMode('manual');
                    }}
                    className="flex-1 py-2.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-xl font-bold text-xs btn-tactile"
                  >
                    Edit in Manual Mode
                  </button>
                  <button
                    type="button"
                    onClick={handleCancelVoice}
                    className="flex-1 py-2.5 bg-gray-100 hover:bg-gray-200 text-gray-500 rounded-xl font-bold text-xs btn-tactile"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* STATE F: SAVING */}
          {voiceState === 'saving' && (
            <div className="bg-white rounded-3xl p-10 border border-indigo-150 shadow-sm text-center space-y-4">
              <div className="w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto"></div>
              <h3 className="text-base font-extrabold text-gray-800">Saving Transaction...</h3>
              <p className="text-xs text-gray-400">Verifying balance & recording entry</p>
            </div>
          )}

          {/* STATE G: SUCCESS */}
          {voiceState === 'success' && savedResult && (
            <div className="bg-white rounded-3xl p-6 sm:p-8 border border-green-200 shadow-sm text-center space-y-6">
              <div className="w-16 h-16 bg-green-100 text-green-600 rounded-full flex items-center justify-center mx-auto">
                <CheckCircle className="w-10 h-10" />
              </div>

              <div className="space-y-1">
                <h3 className="text-xl font-black text-gray-800">{t.saved_success}</h3>
                <span className="text-xs text-gray-400 block">
                  {savedResult.offline ? "Saved locally (Pending sync)" : "Verified on server"}
                </span>
              </div>

              {/* Authoritative Receipt Card */}
              <div className="bg-gray-50 border border-gray-200 rounded-2xl p-4 text-left space-y-2.5">
                <div className="flex justify-between items-center text-sm">
                  <span className="text-gray-500 font-semibold">{t.customer_label}:</span>
                  <span className="font-extrabold text-gray-900">{savedResult.customer_name}</span>
                </div>
                <div className="flex justify-between items-center text-sm">
                  <span className="text-gray-500 font-semibold">{t.type_label}:</span>
                  <span className={`font-black ${savedResult.type === 'credit' ? 'text-red-600' : 'text-green-600'}`}>
                    {savedResult.type === 'credit' ? t.add_credit : t.add_payment}
                  </span>
                </div>
                <div className="flex justify-between items-center text-sm">
                  <span className="text-gray-500 font-semibold">{t.amount_label}:</span>
                  <span className="font-extrabold text-gray-900 text-lg">
                    ₹{(savedResult.amount / 100).toFixed(2)}
                  </span>
                </div>

                {savedResult.current_balance !== null && (
                  <div className="pt-2 border-t border-gray-200 flex justify-between items-center text-sm">
                    <span className="text-indigo-900 font-bold">{t.new_balance}:</span>
                    <span className="font-black text-indigo-700 text-lg">
                      ₹{(Math.abs(savedResult.current_balance) / 100).toFixed(2)}
                    </span>
                  </div>
                )}
              </div>

              {/* Actions: Record Another or Done */}
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={onBack}
                  className="flex-1 py-3.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-2xl font-bold text-sm btn-tactile"
                >
                  {t.done}
                </button>
                <button
                  type="button"
                  onClick={handleResetForAnother}
                  className="flex-1 py-3.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-2xl font-bold text-sm shadow-md shadow-indigo-600/20 btn-tactile flex items-center justify-center gap-1.5"
                >
                  <Plus className="w-4 h-4" />
                  {t.record_another}
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* ======================================================== */}
      {/* 2. MANUAL ENTRY FLOW                                    */}
      {/* ======================================================== */}
      {entryMode === 'manual' && voiceState !== 'success' && (
        <div className="space-y-4">
          {manualError && (
            <div className="bg-red-50 text-red-700 p-3.5 rounded-2xl border border-red-200 text-xs font-semibold">
              {manualError}
            </div>
          )}

          {!manualCust ? (
            // Pick Customer Step
            <div className="space-y-3">
              <div className="relative">
                <Search className="w-5 h-5 text-gray-400 absolute left-3.5 top-3.5" />
                <input
                  type="text"
                  placeholder={t.search_placeholder}
                  value={customerSearch}
                  onChange={(e) => setCustomerSearch(e.target.value)}
                  className="w-full bg-white border border-gray-200 rounded-2xl py-3 pl-11 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm"
                  autoFocus
                />
              </div>

              {loadingCustomers ? (
                <div className="text-center py-6 text-xs text-gray-400">Loading customers...</div>
              ) : filteredCustomers.length === 0 ? (
                <div className="bg-white rounded-2xl p-6 text-center text-xs text-gray-400 italic">
                  {t.no_customers}
                </div>
              ) : (
                <div className="bg-white border border-gray-200 rounded-2xl shadow-sm divide-y divide-gray-100 max-h-80 overflow-y-auto">
                  {filteredCustomers.map(c => (
                    <div
                      key={c.id}
                      onClick={() => setManualCust(c)}
                      className="p-3.5 flex justify-between items-center hover:bg-gray-50 active:bg-gray-100 cursor-pointer text-sm"
                    >
                      <span className="font-bold text-gray-800">{c.name}</span>
                      {c.phone && <span className="text-xs text-gray-400">{c.phone}</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            // Enter Details Step
            <form onSubmit={handleManualSave} className="bg-white rounded-3xl p-6 border border-gray-150 shadow-sm space-y-5">
              <div className="bg-indigo-50 border border-indigo-100 p-3.5 rounded-2xl flex justify-between items-center">
                <div>
                  <span className="text-[10px] uppercase font-bold text-indigo-400 block">{t.customer_label}</span>
                  <span className="text-base font-bold text-indigo-900">{manualCust.name}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setManualCust(null)}
                  className="text-xs font-semibold text-indigo-600 hover:underline"
                >
                  Change
                </button>
              </div>

              {/* Type Toggle */}
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setManualTxType('credit')}
                  className={`py-3.5 rounded-2xl font-bold text-sm border btn-tactile ${
                    manualTxType === 'credit'
                      ? 'bg-red-600 border-red-600 text-white shadow-md'
                      : 'bg-white border-gray-200 text-red-600 hover:bg-red-50'
                  }`}
                >
                  + {t.add_credit}
                </button>
                <button
                  type="button"
                  onClick={() => setManualTxType('payment')}
                  className={`py-3.5 rounded-2xl font-bold text-sm border btn-tactile ${
                    manualTxType === 'payment'
                      ? 'bg-green-600 border-green-600 text-white shadow-md'
                      : 'bg-white border-gray-200 text-green-600 hover:bg-green-50'
                  }`}
                >
                  - {t.add_payment}
                </button>
              </div>

              {/* Amount */}
              <div>
                <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">
                  {t.amount_label}
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  inputMode="decimal"
                  placeholder="0.00"
                  value={manualAmount}
                  onChange={(e) => setManualAmount(e.target.value)}
                  className="w-full bg-gray-50 border border-gray-200 rounded-2xl py-3.5 text-3xl font-extrabold text-center text-gray-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-inner"
                  autoFocus
                  required
                />
              </div>

              {/* Note */}
              <div>
                <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">
                  {t.note_placeholder} (Optional)
                </label>
                <input
                  type="text"
                  placeholder={t.note_placeholder}
                  value={manualNote}
                  onChange={(e) => setManualNote(e.target.value)}
                  className="w-full bg-white border border-gray-200 rounded-xl py-2.5 px-3.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <button
                type="submit"
                disabled={manualSubmitting}
                className={`w-full py-4 px-6 rounded-2xl shadow-lg text-white font-bold flex items-center justify-center gap-2 btn-tactile text-base ${
                  manualTxType === 'credit'
                    ? 'bg-red-600 hover:bg-red-700 shadow-red-600/20'
                    : 'bg-green-600 hover:bg-green-700 shadow-green-600/20'
                }`}
              >
                <Plus className="w-5 h-5" />
                {manualSubmitting ? "Saving..." : manualTxType === 'credit' ? t.add_credit : t.add_payment}
              </button>
            </form>
          )}
        </div>
      )}
    </div>
  );
}

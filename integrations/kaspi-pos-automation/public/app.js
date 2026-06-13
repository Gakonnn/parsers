// ─── Kaspi Pay — Frontend App ───

const API = '';

// ─── State ───

let currentOpId = null;
let invoicePollingTimer = null;
let historyOpId = null;
let qrPollingTimer = null;
let qrCountdownTimer = null;
let qrOperationId = null;

// ─── Helpers ───

const $ = (id) => document.getElementById(id);
const digitsOnly = (str) => str.replace(/\D/g, '');

const getSession = () => {
  try {
    return JSON.parse(localStorage.getItem('kaspi_session') || '{}');
  } catch {
    return {};
  }
};

const sessionHeaders = () => {
  const s = getSession();
  const h = {};
  if (s.tokenSN) h['X-Token-SN'] = s.tokenSN;
  if (s.profileId) h['X-Profile-ID'] = String(s.profileId);
  if (s.vtokenSecret) h['X-Vtoken-Secret'] = s.vtokenSecret;
  return h;
};

const apiFetch = async (path, opts = {}) => {
  opts.headers = { ...sessionHeaders(), ...(opts.headers || {}) };
  const resp = await fetch(API + path, opts);
  return resp.json();
};

const apiPost = (path, body) =>
  apiFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    ...(body !== undefined && { body: JSON.stringify(body) }),
  });

// ─── Session Persistence (localStorage) ───

const SESSION_KEY = 'kaspi_session';

const saveSession = (data) => {
  let prev = {};
  try {
    prev = JSON.parse(localStorage.getItem(SESSION_KEY) || '{}');
  } catch {}
  const merged = { ...prev, ...data };
  if (data.phone) merged.phoneNumber = data.phone;
  localStorage.setItem(SESSION_KEY, JSON.stringify(merged));
};

const clearSession = () => localStorage.removeItem(SESSION_KEY);

const checkSession = async () => {
  try {
    const resp = await apiFetch('/api/session/check');
    if (resp.active === true) return { active: true };
    return { active: false, error: resp.error || 'Сессия неактивна' };
  } catch {
    return { active: false, error: 'Ошибка проверки сессии' };
  }
};

const tryRestoreSession = async () => {
  const session = getSession();
  if (session.tokenSN && session.vtokenSecret) {
    showMainScreen(session);
    // Verify session is still active on the server
    const result = await checkSession();
    if (!result.active) {
      clearSession();
      $('mainScreen').classList.add('hidden');
      $('authScreen').classList.remove('hidden');
      setAuthStep(1);
      showAuthMsg(result.error || 'Сессия истекла. Войдите заново.', 'err');
      return false;
    }
    return true;
  }
  clearSession();
  return false;
};

const updateRefreshAuthBtn = () => {
  const session = getSession();
  const btn = $('btnRefreshAuth');
  if (btn) btn.classList.toggle('hidden', !session.tokenSN || !session.vtokenSecret);
};

const formatPhone = (digits) => {
  // Format up to 10 digits as "XXX XXX XX XX"
  const d = digits.slice(0, 10);
  if (d.length <= 3) return d;
  if (d.length <= 6) return `${d.slice(0, 3)} ${d.slice(3)}`;
  if (d.length <= 8) return `${d.slice(0, 3)} ${d.slice(3, 6)} ${d.slice(6)}`;
  return `${d.slice(0, 3)} ${d.slice(3, 6)} ${d.slice(6, 8)} ${d.slice(8)}`;
};

const shortValue = (value) => {
  if (value === null || value === undefined || value === '') return '—';
  const str = String(value);
  if (str.length <= 18) return str;
  return `${str.slice(0, 8)}...${str.slice(-6)}`;
};

const buildAuthErrorMessage = (body, fallback = 'Ошибка авторизации') => {
  const viewCode = body?.view?.code;
  const clientType = body?.data?.analyticObj?.clientType;
  const headerName = body?.data?.headerName;

  if (viewCode === 'UniversalKaspiIdTakePhoto' || viewCode === 'ViewKaspiIdTakePhoto') {
    return (
      'SMS-код принят, но Kaspi запросил Kaspi ID/фото для регистрации. ' +
      'Это не ошибка кода. Сейчас номер определяется как клиентский аккаунт, а для QR-оплаты нужен аккаунт кассира Kaspi Pay.'
    );
  }

  if (clientType === 'customer' || headerName === 'Registration') {
    return 'Kaspi определил этот номер как клиентский аккаунт/регистрацию. Используйте номер кассира Kaspi Pay.';
  }

  return body?.data?.desc || body?.data?.message || fallback;
};

const attachPhoneFormatter = (el) => {
  el.addEventListener('input', () => {
    const digits = digitsOnly(el.value);
    const formatted = formatPhone(digits);
    if (el.value !== formatted) el.value = formatted;
  });
};

window.addEventListener('DOMContentLoaded', () => {
  updateRefreshAuthBtn();
  tryRestoreSession();
  attachPhoneFormatter($('phoneInput'));
  attachPhoneFormatter($('clientPhone'));
});

// ─── Auth UI Helpers ───

const setAuthStep = (n) => {
  const panelByStep = {
    1: 'authStep1',
    password: 'authStepPassword',
    2: 'authStep2',
    3: 'authStep3',
  };
  Object.values(panelByStep).forEach((id) => $(id)?.classList.add('hidden'));
  $(panelByStep[n])?.classList.remove('hidden');

  const dotStep = n === 'password' ? 2 : Number(n);
  for (let i = 1; i <= 3; i++) {
    $(`dot${i}`).className = `step-dot${i < dotStep ? ' done' : i === dotStep ? ' active' : ''}`;
  }
};

const showAuthMsg = (msg, type) => {
  const el = $('authMsg');
  if (!msg) {
    el.classList.add('hidden');
    return;
  }
  el.className = `status-bar status-${type}`;
  el.textContent = msg;
  el.classList.remove('hidden');
};

const resetAuth = () => {
  setAuthStep(1);
  $('otpInput').value = '';
  $('passwordInput').value = '';
  showAuthMsg('', '');
};

// ─── Auth Flow ───

let authProcessId = null;

const sendPhone = async () => {
  const phone = digitsOnly($('phoneInput').value);
  if (phone.length < 10) return showAuthMsg('Введите 10 цифр номера', 'err');

  const btn = $('btnSendPhone');
  btn.disabled = true;
  btn.innerHTML = 'Отправка...<span class="loader"></span>';
  showAuthMsg('', '');

  try {
    const init = await apiPost('/api/auth/init');
    if (!init.success) {
      showAuthMsg(`Ошибка инициализации: ${JSON.stringify(init.body)}`, 'err');
      return;
    }

    authProcessId = init.processId;

    const resp = await apiPost('/api/auth/send-phone', { phoneNumber: phone, processId: authProcessId });
    if (resp.success) {
      $('otpDesc').textContent = resp.desc || `SMS отправлен на +7${phone}`;
      setAuthStep(2);
    } else if (resp.step === 'password_required' || resp.view === 'KPEnterLoginPassword') {
      $('passwordDesc').textContent = `Kaspi запросил пароль для номера +7${formatPhone(phone)}. Введите пароль аккаунта кассира Kaspi Pay.`;
      $('passwordInput').value = '';
      setAuthStep('password');
    } else {
      const clientType = resp.body?.data?.analyticObj?.clientType;
      const hint =
        clientType === 'customer'
          ? 'Этот номер Kaspi определил как клиентский аккаунт. Для QR-оплаты нужен аккаунт кассира Kaspi Pay.'
          : '';
      showAuthMsg(`Ошибка: ${hint || buildAuthErrorMessage(resp.body)}`, 'err');
    }
  } catch (e) {
    showAuthMsg(`Ошибка сети: ${e.message}`, 'err');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Получить SMS код';
  }
};

const submitPassword = async () => {
  const password = $('passwordInput').value.trim();
  if (!password) return showAuthMsg('Введите пароль', 'err');

  const btn = $('btnSubmitPassword');
  btn.disabled = true;
  btn.innerHTML = 'Проверка...<span class="loader"></span>';
  showAuthMsg('', '');

  try {
    const resp = await apiPost('/api/auth/submit-password', { password, processId: authProcessId });
    if (resp.success && resp.step === 'finished') {
      saveSession(resp);
      authProcessId = null;
      $('passwordInput').value = '';
      showMainScreen(resp);
    } else if (resp.step === 'otp_required') {
      $('otpDesc').textContent = resp.desc || 'Kaspi отправил SMS-код для подтверждения входа';
      setAuthStep(2);
    } else if (resp.step === 'password_required') {
      showAuthMsg('Kaspi не принял пароль. Проверьте пароль аккаунта кассира Kaspi Pay.', 'err');
    } else {
      const clientType = resp.body?.data?.analyticObj?.clientType;
      const hint =
        clientType === 'customer'
          ? 'Kaspi всё еще видит этот номер как клиентский аккаунт. Нужен аккаунт кассира Kaspi Pay.'
          : '';
      showAuthMsg(`Ошибка входа: ${hint || buildAuthErrorMessage(resp.body)}`, 'err');
    }
  } catch (e) {
    showAuthMsg(`Ошибка: ${e.message}`, 'err');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Продолжить';
  }
};

const verifyOtp = async () => {
  const otp = digitsOnly($('otpInput').value);
  if (!otp) return showAuthMsg('Введите код', 'err');

  const btn = $('btnVerifyOtp');
  btn.disabled = true;
  btn.innerHTML = 'Проверка...<span class="loader"></span>';
  showAuthMsg('', '');

  try {
    const resp = await apiPost('/api/auth/verify-otp', { otp, processId: authProcessId });
    if (resp.success && resp.step === 'finished') {
      saveSession(resp);
      authProcessId = null;
      showMainScreen(resp);
    } else {
      showAuthMsg(buildAuthErrorMessage(resp.body, 'Kaspi не завершил авторизацию'), 'err');
    }
  } catch (e) {
    showAuthMsg(`Ошибка: ${e.message}`, 'err');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Подтвердить';
  }
};

// ─── Main Screen ───

const showMainScreen = (data) => {
  $('authScreen').classList.add('hidden');
  $('mainScreen').classList.remove('hidden');
  if (data) {
    $('userName').textContent = data.phone || '—';
    $('userOrg').textContent = data.orgName || '—';
    $('userAvatar').textContent = (data.orgName || 'K')[0].toUpperCase();
    renderSessionEnv(data);
  }
};

const renderSessionEnv = (data = getSession()) => {
  const tokenSN = data.tokenSN || '';
  const vtokenSecret = data.vtokenSecret || '';
  const profileId = data.profileId || '';
  const envText = [
    `KASPI_POS_TOKEN_SN=${tokenSN}`,
    `KASPI_POS_VTOKEN_SECRET=${vtokenSecret}`,
    `KASPI_POS_PROFILE_ID=${profileId}`,
  ].join('\n');

  $('tokenSnPreview').textContent = shortValue(tokenSN);
  $('profileIdPreview').textContent = profileId || '—';
  $('sessionEnv').value = envText;
  $('sessionCard').classList.toggle('hidden', !tokenSN || !vtokenSecret);
};

const copySessionEnv = async () => {
  const text = $('sessionEnv').value;
  const msg = $('sessionCopyMsg');
  try {
    await navigator.clipboard.writeText(text);
    msg.textContent = 'Данные скопированы.';
    msg.className = 'status-bar status-ok';
  } catch {
    $('sessionEnv').select();
    document.execCommand('copy');
    msg.textContent = 'Данные выделены и скопированы.';
    msg.className = 'status-bar status-ok';
  }
  msg.classList.remove('hidden');
};

const logout = async () => {
  const { tokenSN } = getSession();
  clearSession();
  await apiPost('/api/auth/logout', { tokenSN });
  $('mainScreen').classList.add('hidden');
  $('authScreen').classList.remove('hidden');
  $('phoneInput').value = '';
  $('otpInput').value = '';
  $('passwordInput').value = '';
  setAuthStep(1);
  showAuthMsg('', '');
};


const switchTab = (tab) => {
  $('invoiceTab').classList.toggle('hidden', tab !== 'invoice');
  $('qrTab').classList.toggle('hidden', tab !== 'qr');
  $('historyTab').classList.toggle('hidden', tab !== 'history');
  $('salesTab').classList.toggle('hidden', tab !== 'sales');
  $('tabInvoice').classList.toggle('active', tab === 'invoice');
  $('tabQr').classList.toggle('active', tab === 'qr');
  $('tabHistory').classList.toggle('active', tab === 'history');
  $('tabSales').classList.toggle('active', tab === 'sales');
  if (tab === 'history') loadHistory();
  if (tab === 'sales') loadSales();
};

// ─── Invoice ───

const statusBadge = (status) => {
  const map = {
    RemotePaymentCreated: ['Ожидает оплаты', 'pending'],
    RemotePaymentPaid: ['Оплачен', 'paid'],
    RemotePaymentCanceled: ['Отменён', 'canceled'],
    RemotePaymentExpired: ['Истёк', 'expired'],
  };
  const [label, cls] = map[status] || [status, 'pending'];
  return `<span class="badge badge-${cls}">${label}</span>`;
};

const renderDetails = (data, containerId) => {
  if (!data) return;
  const el = $(containerId);
  const rows = (data.DynamicDetails || [])
    .sort((a, b) => a.Order - b.Order)
    .map(
      ({ Title, Data, IsBold }) =>
        `<div class="detail-row">
        <span class="detail-label">${Title}</span>
        <span class="detail-value" style="${IsBold ? 'font-weight:700' : ''}">${Data}</span>
      </div>`,
    )
    .join('');
  el.innerHTML = `<div style="text-align:center;margin:12px 0;">${statusBadge(data.Status)}</div>${rows}`;
};

const stopInvoicePolling = () => {
  if (invoicePollingTimer) {
    clearInterval(invoicePollingTimer);
    invoicePollingTimer = null;
  }
};

const refreshInvoice = async () => {
  if (!currentOpId) return null;
  try {
    const resp = await apiFetch(`/api/invoice/details?operationId=${currentOpId}`);
    renderDetails(resp.Data, 'invoiceDetails');
    const { Status: status } = resp.Data || {};
    $('btnCancel').classList.toggle('hidden', status !== 'RemotePaymentCreated');
    if (status && status !== 'RemotePaymentCreated') stopInvoicePolling();
    return status;
  } catch (e) {
    console.error(e);
    return null;
  }
};

const startInvoicePolling = () => {
  stopInvoicePolling();
  refreshInvoice();
  invoicePollingTimer = setInterval(refreshInvoice, 5000);
};

const createInvoice = async () => {
  const phone = digitsOnly($('clientPhone').value);
  const amount = $('invoiceAmount').value;
  const comment = $('invoiceComment').value || 'Оплата';
  if (!phone || !amount) return alert('Заполните телефон и сумму');

  const btn = $('btnCreate');
  btn.disabled = true;
  btn.innerHTML = 'Создание...<span class="loader"></span>';

  try {
    const resp = await apiPost('/api/invoice/create', {
      phoneNumber: phone,
      amount: Number(amount),
      comment,
    });

    if (resp.Data?.QrOperationId) {
      currentOpId = resp.Data.QrOperationId;
      $('invoiceOpId').textContent = `#${currentOpId}`;
      $('invoiceResult').classList.remove('hidden');
      $('clientPhone').value = '';
      $('invoiceAmount').value = '';
      $('invoiceComment').value = '';
      $('clientInfo').classList.add('hidden');
      startInvoicePolling();
    } else {
      alert(`Ошибка: ${resp.Message || JSON.stringify(resp)}`);
    }
  } catch (e) {
    alert(`Ошибка: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Выставить счёт';
  }
};

const cancelInvoice = async () => {
  if (!currentOpId || !confirm('Отменить счёт?')) return;
  try {
    await apiPost('/api/invoice/cancel', { operationId: currentOpId });
    refreshInvoice();
  } catch (e) {
    alert(`Ошибка: ${e.message}`);
  }
};

// ─── QR Code ───

const FINAL_QR_STATUSES = [
  'Paid',
  'CancelledByUser',
  'NotConfirmedByUser',
  'QrTokenDiscarded',
  'ProcessingFailed',
  'InsufficientFunds',
  'Error',
];

const qrStatusBadge = (status) => {
  const map = {
    QrTokenCreated: ['Ожидание сканирования', 'info'],
    QrTokenScanned: ['Отсканирован', 'info'],
    PaymentConfirmation: ['Подтверждение оплаты...', 'warn'],
    Paid: ['Оплачено ✅', 'ok'],
    CancelledByUser: ['Отменено клиентом', 'err'],
    NotConfirmedByUser: ['Не подтверждено', 'err'],
    QrTokenDiscarded: ['QR не отсканирован', 'err'],
    ProcessingFailed: ['Ошибка обработки', 'err'],
    InsufficientFunds: ['Недостаточно средств', 'err'],
    Error: ['Ошибка', 'err'],
  };
  const [label, cls] = map[status] || [status, 'info'];
  return { label, cls };
};

const stopQrPolling = () => {
  if (qrPollingTimer) {
    clearInterval(qrPollingTimer);
    qrPollingTimer = null;
  }
  if (qrCountdownTimer) {
    clearInterval(qrCountdownTimer);
    qrCountdownTimer = null;
  }
};

const pollQrStatus = async () => {
  if (!qrOperationId) return;
  try {
    const resp = await apiFetch(`/api/qr/status?qrOperationId=${qrOperationId}`);
    const status = resp.Data?.Status;
    if (status) {
      const { label, cls } = qrStatusBadge(status);
      const el = $('qrStatus');
      el.className = `status-bar status-${cls}`;
      el.textContent = label;
    }
    if (FINAL_QR_STATUSES.includes(status)) {
      stopQrPolling();
    }
  } catch (e) {
    console.error('QR polling error:', e);
  }
};

const startQrCountdown = (seconds) => {
  let remaining = seconds;
  const timerEl = $('qrTimer');
  const tick = () => {
    const m = Math.floor(remaining / 60);
    const s = remaining % 60;
    timerEl.textContent = `Осталось: ${m}:${String(s).padStart(2, '0')}`;
    if (remaining <= 0) {
      timerEl.textContent = 'Время истекло';
      stopQrPolling();
    }
    remaining--;
  };
  tick();
  qrCountdownTimer = setInterval(tick, 1000);
};

const generateQrSvg = (text, size = 256) => {
  // Simple QR placeholder using a data URL image via an API
  // For production, use a proper QR library; here we use a public API fallback
  return `<img src="https://api.qrserver.com/v1/create-qr-code/?size=${size}x${size}&data=${encodeURIComponent(text)}" alt="QR Code" style="max-width:100%;border-radius:8px;">`;
};

const createQr = async () => {
  const amount = $('qrAmount').value;
  if (!amount) return alert('Введите сумму');

  const btn = $('btnCreateQr');
  btn.disabled = true;
  btn.innerHTML = 'Создание...<span class="loader"></span>';

  stopQrPolling();

  try {
    const resp = await apiPost('/api/qr/create', { amount: Number(amount) });

    if (resp.Data?.QrToken) {
      qrOperationId = resp.Data.QrOperationId;
      const options = resp.Data.QrPaymentBehaviorOptions || {};
      const pollInterval = (parseInt(options.qrCodeScanEventPollingInterval) || 3) * 1000;
      const waitTimeout = parseInt(options.qrCodeScanWaitTimeout) || 180;

      $('qrCodeContainer').innerHTML = generateQrSvg(resp.Data.QrToken);
      $('qrStatus').className = 'status-bar status-info';
      $('qrStatus').textContent = 'Ожидание сканирования...';
      $('qrResult').classList.remove('hidden');
      $('qrAmount').value = '';

      startQrCountdown(waitTimeout);
      qrPollingTimer = setInterval(pollQrStatus, pollInterval);
    } else {
      alert(`Ошибка: ${resp.Message || JSON.stringify(resp)}`);
    }
  } catch (e) {
    alert(`Ошибка: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Создать QR';
  }
};

const resetQr = () => {
  stopQrPolling();
  qrOperationId = null;
  $('qrResult').classList.add('hidden');
  $('qrCodeContainer').innerHTML = '';
  $('qrTimer').textContent = '';
};

// ─── Client Phone Lookup ───

$('clientPhone').addEventListener('blur', async function () {
  const phone = digitsOnly(this.value);
  const info = $('clientInfo');
  if (phone.length < 10) {
    info.classList.add('hidden');
    return;
  }
  try {
    const resp = await apiFetch(`/api/invoice/client-info?phoneNumber=${phone}`);
    if (resp.Data?.ClientName) {
      info.textContent = `✓ ${resp.Data.ClientName} (${resp.Data.ClientStatus})`;
      info.style.background = '#e8f5e9';
      info.style.color = '#2e7d32';
      info.classList.remove('hidden');
    } else {
      info.textContent = '✗ Клиент не найден';
      info.style.background = '#ffebee';
      info.style.color = '#c62828';
      info.classList.remove('hidden');
    }
  } catch {
    info.classList.add('hidden');
  }
});

// ─── History ───

const loadHistory = async () => {
  const list = $('historyList');
  list.innerHTML =
    '<p style="text-align:center;color:#888;">Загрузка...<span class="loader" style="border-color:#888;border-top-color:transparent;"></span></p>';
  try {
    const resp = await apiPost('/api/invoice/history');
    const ops = resp.Data?.Operations || [];
    if (!ops.length) {
      list.innerHTML = '<p style="text-align:center;color:#888;">Нет операций</p>';
      return;
    }
    list.innerHTML = ops
      .map(
        (op) => `
        <div class="op-item" onclick="showHistoryDetail(${op.Id})">
          <div class="op-row">
            <div>
              <div class="op-name">${op.ClientName || op.ClientShortName || '—'}</div>
              <div class="op-date">${new Date(op.OrderRegDate).toLocaleString('ru')}</div>
            </div>
            <div style="text-align:right;">
              <div class="op-amount">${op.Amount}</div>
              ${statusBadge(op.Status)}
            </div>
          </div>
        </div>`,
      )
      .join('');
  } catch (e) {
    list.innerHTML = `<p style="color:#c62828;">Ошибка: ${e.message}</p>`;
  }
};

const showHistoryDetail = async (opId) => {
  historyOpId = opId;
  const panel = $('historyDetail');
  const content = $('historyDetailContent');
  content.innerHTML = '<p style="text-align:center;">Загрузка...</p>';
  panel.classList.remove('hidden');
  try {
    const resp = await apiFetch(`/api/invoice/details?operationId=${opId}`);
    renderDetails(resp.Data, 'historyDetailContent');
    $('btnCancelFromHistory').classList.toggle('hidden', resp.Data?.Status !== 'RemotePaymentCreated');
  } catch {
    content.innerHTML = '<p style="color:#c62828;">Ошибка</p>';
  }
};

const cancelFromHistory = async () => {
  if (!historyOpId || !confirm('Отменить счёт?')) return;
  try {
    await apiPost('/api/invoice/cancel', { operationId: historyOpId });
    showHistoryDetail(historyOpId);
    loadHistory();
  } catch (e) {
    alert(`Ошибка: ${e.message}`);
  }
};

// ─── Sales (operations history + details + refund) ───

let salesOpId = null;

const loadSales = async () => {
  const list = $('salesList');
  const stats = $('salesStats');
  list.innerHTML =
    '<p style="text-align:center;color:#888;">Загрузка...<span class="loader" style="border-color:#888;border-top-color:transparent;"></span></p>';
  stats.innerHTML = '';
  try {
    const now = new Date();
    const endDate =
      now.getFullYear() +
      '-' +
      String(now.getMonth() + 1).padStart(2, '0') +
      '-' +
      String(now.getDate()).padStart(2, '0') +
      'T23:59:59.000+0500';
    const resp = await apiPost('/api/history/operations', { endDate });
    const data = resp.Data || {};
    // Stats
    const s = data.Statistic || {};
    stats.innerHTML = `<div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
      <div style="background:#e8f5e9;padding:8px 14px;border-radius:10px;text-align:center;"><div style="font-size:12px;color:#2e7d32;">Продажи</div><div style="font-weight:700;color:#2e7d32;">${s.SalesAmount ?? 0} ₸</div><div style="font-size:11px;color:#888;">${s.SalesCount ?? 0} шт</div></div>
      <div style="background:#ffebee;padding:8px 14px;border-radius:10px;text-align:center;"><div style="font-size:12px;color:#c62828;">Возвраты</div><div style="font-weight:700;color:#c62828;">${s.ReturnsAmount ?? 0} ₸</div><div style="font-size:11px;color:#888;">${s.ReturnsCount ?? 0} шт</div></div>
    </div>`;
    // Operations list
    const dailySets = data.DailySets || [];
    if (!dailySets.length) {
      list.innerHTML = '<p style="text-align:center;color:#888;">Нет операций</p>';
      return;
    }
    let html = '';
    for (const day of dailySets) {
      html += `<div style="font-size:13px;color:#888;margin:12px 0 4px;font-weight:600;">${day.Date || ''}</div>`;
      for (const op of day.Operations || []) {
        const isReturn = op.OperationType === 1;
        const sign = isReturn ? '+' : '';
        const color = isReturn ? '#c62828' : '#1a1a1a';
        html += `<div class="op-item" onclick="showSalesDetail(${op.Id}, ${op.OperationMethod || 0})">
          <div class="op-row">
            <div>
              <div class="op-name">${op.ClientName || op.ClientShortName || '—'}</div>
              <div class="op-date">${op.Time || ''}</div>
            </div>
            <div style="text-align:right;">
              <div class="op-amount" style="color:${color};">${sign}${op.Amount} ₸</div>
            </div>
          </div>
        </div>`;
      }
    }
    list.innerHTML = html;
  } catch (e) {
    list.innerHTML = `<p style="color:#c62828;">Ошибка: ${e.message}</p>`;
  }
};

const showSalesDetail = async (id, operationMethod) => {
  salesOpId = id;
  const panel = $('salesDetail');
  const content = $('salesDetailContent');
  const refundSection = $('refundSection');
  const refundMsg = $('refundMsg');
  content.innerHTML = '<p style="text-align:center;">Загрузка...</p>';
  refundSection.classList.add('hidden');
  refundMsg.classList.add('hidden');
  panel.classList.remove('hidden');
  try {
    const resp = await apiPost('/api/history/details', { id, operationMethod: operationMethod || 0 });
    const d = resp.Data || {};
    let rows = '';
    const fields = [
      ['Сумма', d.Amount ? `${d.Amount} ₸` : null],
      ['Клиент', d.ClientName || d.ClientShortName],
      ['Дата', d.OrderRegDate ? new Date(d.OrderRegDate).toLocaleString('ru') : null],
      ['Статус', d.StatusDescription],
      ['Доступно к возврату', d.AvailableReturnAmount != null ? `${d.AvailableReturnAmount} ₸` : null],
      ['Тип возврата', d.PossibleReturnType],
      ['Чек', d.ReceiptUrl ? `<a href="${d.ReceiptUrl}" target="_blank">Открыть</a>` : null],
    ];
    for (const [label, value] of fields) {
      if (value != null)
        rows += `<div class="detail-row"><span class="detail-label">${label}</span><span class="detail-value">${value}</span></div>`;
    }
    // Returns history
    if (d.Returns && d.Returns.length) {
      rows += '<div style="margin-top:12px;font-weight:600;font-size:14px;">Возвраты:</div>';
      for (const r of d.Returns) {
        rows += `<div class="detail-row"><span class="detail-label">${r.Date || ''}</span><span class="detail-value" style="color:#c62828;">${r.Amount} ₸</span></div>`;
      }
    }
    content.innerHTML = rows || '<p style="color:#888;">Нет данных</p>';
    // Show refund if available
    const returnAmount = parseFloat(String(d.AvailableReturnAmount || '0').replace(/[^\d.]/g, ''));
    if (returnAmount > 0) {
      $('refundAmount').value = returnAmount;
      $('refundAmount').max = returnAmount;
      refundSection.classList.remove('hidden');
    }
  } catch (e) {
    content.innerHTML = `<p style="color:#c62828;">Ошибка: ${e.message}</p>`;
  }
};

const createRefund = async () => {
  const amount = $('refundAmount').value;
  if (!salesOpId || !amount) return alert('Укажите сумму возврата');
  if (!confirm(`Вернуть ${amount} ₸?`)) return;
  const btn = $('btnRefund');
  const msg = $('refundMsg');
  btn.disabled = true;
  btn.innerHTML = 'Возврат...<span class="loader"></span>';
  msg.classList.add('hidden');
  try {
    const resp = await apiPost('/api/refund/create', { qrOperationId: salesOpId, returnAmount: Number(amount) });
    if (resp.StatusCode === 0) {
      msg.className = 'status-bar status-ok';
      msg.textContent = 'Возврат выполнен успешно';
    } else {
      msg.className = 'status-bar status-err';
      msg.textContent = resp.Description || resp.Message || 'Ошибка возврата';
    }
    msg.classList.remove('hidden');
    // Refresh detail
    showSalesDetail(salesOpId, 0);
  } catch (e) {
    msg.className = 'status-bar status-err';
    msg.textContent = `Ошибка: ${e.message}`;
    msg.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Сделать возврат';
  }
};

// ─── Expose to HTML onclick handlers ───

Object.assign(window, {
  sendPhone,
  submitPassword,
  verifyOtp,
  copySessionEnv,
  resetAuth,
  logout,
  switchTab,
  createInvoice,
  refreshInvoice,
  cancelInvoice,
  createQr,
  resetQr,
  loadHistory,
  showHistoryDetail,
  cancelFromHistory,
  loadSales,
  showSalesDetail,
  createRefund,
});

// ─── Init ───

(() => {
  setAuthStep(1);
  const session = getSession();
  if (session.tokenSN && session.vtokenSecret) {
    showMainScreen(session);
  }
})();

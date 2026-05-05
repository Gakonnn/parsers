const configuredApiBase = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

const authScript = `
(() => {
  const TOKEN_KEY = "parsers_platform_token";
  const configuredApiBase = ${JSON.stringify(configuredApiBase)};
  const apiBase = configuredApiBase || window.location.protocol + "//" + window.location.hostname + ":8000/api/v1";

  function humanize(message) {
    if (message === "Incorrect email or password") return "Неверный email или пароль.";
    if (message === "User with this email already exists") return "Пользователь с таким email уже зарегистрирован.";
    if (message === "User account is disabled") return "Аккаунт отключен. Обратитесь к администратору.";
    return message || "Не удалось выполнить запрос.";
  }

  function ready(fn) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn, { once: true });
    else fn();
  }

  ready(() => {
    if (window.localStorage.getItem(TOKEN_KEY)) {
      window.location.replace("/dashboard");
      return;
    }

    const form = document.querySelector("[data-auth-form]");
    const modeInput = document.querySelector("[data-auth-mode]");
    const nameField = document.querySelector("[data-name-field]");
    const title = document.querySelector("[data-auth-title]");
    const helper = document.querySelector("[data-auth-helper]");
    const submit = document.querySelector("[data-auth-submit]");
    const message = document.querySelector("[data-auth-message]");
    const tabs = Array.from(document.querySelectorAll("[data-auth-tab]"));

    function setMode(mode) {
      if (!modeInput || !nameField || !title || !helper || !submit) return;
      const isRegister = mode === "register";
      modeInput.value = mode;
      nameField.hidden = !isRegister;
      const nameInput = nameField.querySelector("input");
      if (nameInput) nameInput.required = isRegister;
      title.textContent = isRegister ? "Создать аккаунт" : "Войти в кабинет";
      helper.textContent = isRegister
        ? "Если аккаунта ещё нет, зарегистрируйтесь. Первый пользователь станет администратором."
        : "Введите email и пароль существующего аккаунта.";
      submit.textContent = isRegister ? "Создать аккаунт" : "Войти";
      tabs.forEach((button) => button.classList.toggle("active", button.dataset.authTab === mode));
      if (message) message.textContent = "";
    }

    tabs.forEach((button) => {
      button.addEventListener("click", () => setMode(button.dataset.authTab || "login"));
    });

    if (!form) return;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!submit || !message || !modeInput) return;
      message.textContent = "";
      submit.disabled = true;
      const originalText = submit.textContent;
      submit.textContent = "Проверяем...";

      const formData = new FormData(form);
      const mode = modeInput.value === "register" ? "register" : "login";
      const payload = {
        email: String(formData.get("email") || "").trim(),
        password: String(formData.get("password") || ""),
      };
      if (mode === "register") payload.full_name = String(formData.get("full_name") || "").trim() || null;

      try {
        const response = await fetch(apiBase + "/auth/" + mode, {
          method: "POST",
          headers: { "Accept": "application/json", "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const raw = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(humanize(raw.detail));
        window.localStorage.setItem(TOKEN_KEY, raw.access_token);
        window.location.replace("/dashboard");
      } catch (error) {
        message.textContent = error instanceof Error ? humanize(error.message) : "Не удалось выполнить запрос.";
        submit.disabled = false;
        submit.textContent = originalText;
      }
    });
  });
})();
`;

export default function HomePage() {
  return (
    <main className="auth-page">
      <section className="hero-panel">
        <div className="hero-topline">
          <span className="brand-mark">P</span>
          <span>ParserDesk</span>
        </div>
        <div className="hero-copy">
          <span className="eyebrow">Commercial parser operations</span>
          <h1>Кабинет для парсеров, который выглядит как рабочий продукт, а не временная админка.</h1>
          <p>
            Управление задачами, тарифами, пользователями, оплатами, уведомлениями и результатами PostgreSQL в одном аккуратном интерфейсе.
          </p>
        </div>
        <div className="hero-metrics">
          <div><strong>4</strong><span>источника</span></div>
          <div><strong>live</strong><span>прогресс</span></div>
          <div><strong>CSV/XLSX</strong><span>экспорт</span></div>
        </div>
      </section>

      <section className="auth-card">
        <div className="auth-tabs">
          <button className="active" type="button" data-auth-tab="login">Вход</button>
          <button type="button" data-auth-tab="register">Регистрация</button>
        </div>
        <div>
          <span className="eyebrow">Secure access</span>
          <h2 data-auth-title>Войти в кабинет</h2>
          <p className="auth-helper" data-auth-helper>Введите email и пароль существующего аккаунта.</p>
        </div>
        <form data-auth-form>
          <input type="hidden" name="mode" value="login" data-auth-mode />
          <label className="field-block" data-name-field hidden>
            <span>Имя</span>
            <input name="full_name" placeholder="Ваше имя" autoComplete="name" />
          </label>
          <label className="field-block">
            <span>Email</span>
            <input name="email" type="email" placeholder="name@company.kz" autoComplete="email" required />
          </label>
          <label className="field-block">
            <span>Пароль</span>
            <input name="password" type="password" minLength={8} autoComplete="current-password" required />
          </label>
          <button className="primary-button wide" type="submit" data-auth-submit>Войти</button>
          <p className="form-message error" data-auth-message aria-live="polite" />
        </form>
        <p className="auth-note">Первый зарегистрированный пользователь автоматически получает роль администратора.</p>
      </section>
      <script dangerouslySetInnerHTML={{ __html: authScript }} />
    </main>
  );
}

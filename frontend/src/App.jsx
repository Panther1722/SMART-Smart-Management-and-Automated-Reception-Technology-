import React, { useEffect, useMemo, useRef, useState } from "react";

const SESSION_STORAGE_KEY = "smart_session_id";
const SESSION_TOKEN_KEY = "smart_session_token";
const EMAIL_STORAGE_KEY = "smart_guest_email";
const LANGUAGE_STORAGE_KEY = "smart_language";

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "de", label: "Deutsch" },
  { code: "fr", label: "Français" },
  { code: "it", label: "Italiano" },
  { code: "es", label: "Español" },
];

const COPY = {
  en: {
    eyebrow: "AI Receptionist",
    welcome: "Welcome",
    landingSubtitle: "Your AI receptionist is ready to help with bookings, questions, and more.",
    languageLabel: "Language",
    start: "Start",
    appTitle: "AI Receptionist Prototype",
    headerEmail: "Enter your email to start chatting with our receptionist.",
    headerChat: (email) =>
      `Chatting as ${email}. Your session is saved in this browser tab.`,
    checkingSession: "Checking your session…",
    beforeWeBegin: "Before we begin",
    emailLead:
      "Please share your email so we can send booking confirmations and updates.",
    emailLabel: "Email address",
    emailPlaceholder: "you@example.com",
    emailRequired: "Please enter your email address.",
    emailInvalid: "Please enter a valid email address.",
    sessionStartError: (msg) => `Could not start session. ${msg}`,
    sessionStartNetworkError:
      "Could not reach the server. Run `docker compose up` and open http://localhost:8080.",
    continueToChat: "Continue to chat",
    starting: "Starting…",
    chatAriaLabel: "Chat",
    assistantTyping: "Assistant is typing",
    messageLabel: "Message",
    loadingHistory: "Loading chat history…",
    waitingReply: "Waiting for reply…",
    typeMessage: "Type a message…",
    send: "Send",
    sending: "Sending…",
    greeting:
      "Hi! I'm the (prototype) receptionist. What can I help you with today?",
    defaultReply: "Thanks — I've received your message.",
    sendError: (msg) => `Sorry — I couldn't send that message. ${msg}`,
    footerApiDocs: "Backend API Docs",
    footerSavedRequests: "View Saved Requests (JSON)",
    landingAriaLabel: "Welcome",
  },
  de: {
    eyebrow: "KI-Rezeptionist",
    welcome: "Willkommen",
    landingSubtitle: "Ihr KI-Rezeptionist hilft bei Buchungen, Fragen und mehr.",
    languageLabel: "Sprache",
    start: "Starten",
    appTitle: "KI-Rezeptionist Prototyp",
    headerEmail: "Geben Sie Ihre E-Mail ein, um mit unserem Rezeptionisten zu chatten.",
    headerChat: (email) =>
      `Chat als ${email}. Ihre Sitzung ist in diesem Browser-Tab gespeichert.`,
    checkingSession: "Sitzung wird überprüft…",
    beforeWeBegin: "Bevor wir beginnen",
    emailLead:
      "Bitte geben Sie Ihre E-Mail an, damit wir Buchungsbestätigungen und Updates senden können.",
    emailLabel: "E-Mail-Adresse",
    emailPlaceholder: "sie@beispiel.de",
    emailRequired: "Bitte geben Sie Ihre E-Mail-Adresse ein.",
    emailInvalid: "Bitte geben Sie eine gültige E-Mail-Adresse ein.",
    sessionStartError: (msg) => `Sitzung konnte nicht gestartet werden. ${msg}`,
    continueToChat: "Weiter zum Chat",
    starting: "Wird gestartet…",
    chatAriaLabel: "Chat",
    assistantTyping: "Assistent schreibt",
    messageLabel: "Nachricht",
    loadingHistory: "Chatverlauf wird geladen…",
    waitingReply: "Warte auf Antwort…",
    typeMessage: "Nachricht eingeben…",
    send: "Senden",
    sending: "Wird gesendet…",
    greeting:
      "Hallo! Ich bin der (Prototyp-)Rezeptionist. Womit kann ich Ihnen heute helfen?",
    defaultReply: "Danke — ich habe Ihre Nachricht erhalten.",
    sendError: (msg) => `Entschuldigung — Nachricht konnte nicht gesendet werden. ${msg}`,
    footerApiDocs: "Backend-API-Dokumentation",
    footerSavedRequests: "Gespeicherte Anfragen anzeigen (JSON)",
    landingAriaLabel: "Willkommen",
  },
  fr: {
    eyebrow: "Réceptionniste IA",
    welcome: "Bienvenue",
    landingSubtitle:
      "Votre réceptionniste IA est prêt à vous aider pour les réservations et vos questions.",
    languageLabel: "Langue",
    start: "Commencer",
    appTitle: "Prototype de réceptionniste IA",
    headerEmail: "Entrez votre e-mail pour discuter avec notre réceptionniste.",
    headerChat: (email) =>
      `Discussion en tant que ${email}. Votre session est enregistrée dans cet onglet.`,
    checkingSession: "Vérification de votre session…",
    beforeWeBegin: "Avant de commencer",
    emailLead:
      "Veuillez partager votre e-mail pour recevoir les confirmations de réservation et les mises à jour.",
    emailLabel: "Adresse e-mail",
    emailPlaceholder: "vous@exemple.fr",
    emailRequired: "Veuillez saisir votre adresse e-mail.",
    emailInvalid: "Veuillez saisir une adresse e-mail valide.",
    sessionStartError: (msg) => `Impossible de démarrer la session. ${msg}`,
    continueToChat: "Continuer vers le chat",
    starting: "Démarrage…",
    chatAriaLabel: "Chat",
    assistantTyping: "L'assistant écrit",
    messageLabel: "Message",
    loadingHistory: "Chargement de l'historique…",
    waitingReply: "En attente de réponse…",
    typeMessage: "Saisissez un message…",
    send: "Envoyer",
    sending: "Envoi…",
    greeting:
      "Bonjour ! Je suis le réceptionniste (prototype). Comment puis-je vous aider aujourd'hui ?",
    defaultReply: "Merci — j'ai bien reçu votre message.",
    sendError: (msg) => `Désolé — impossible d'envoyer ce message. ${msg}`,
    footerApiDocs: "Documentation API backend",
    footerSavedRequests: "Voir les demandes enregistrées (JSON)",
    landingAriaLabel: "Bienvenue",
  },
  it: {
    eyebrow: "Receptionist AI",
    welcome: "Benvenuto",
    landingSubtitle:
      "Il receptionist AI è pronto ad aiutarti con prenotazioni, domande e altro.",
    languageLabel: "Lingua",
    start: "Inizia",
    appTitle: "Prototipo receptionist AI",
    headerEmail: "Inserisci la tua e-mail per chattare con il nostro receptionist.",
    headerChat: (email) =>
      `Chat come ${email}. La sessione è salvata in questa scheda del browser.`,
    checkingSession: "Verifica della sessione…",
    beforeWeBegin: "Prima di iniziare",
    emailLead:
      "Condividi la tua e-mail per ricevere conferme di prenotazione e aggiornamenti.",
    emailLabel: "Indirizzo e-mail",
    emailPlaceholder: "tu@esempio.it",
    emailRequired: "Inserisci il tuo indirizzo e-mail.",
    emailInvalid: "Inserisci un indirizzo e-mail valido.",
    sessionStartError: (msg) => `Impossibile avviare la sessione. ${msg}`,
    continueToChat: "Continua alla chat",
    starting: "Avvio…",
    chatAriaLabel: "Chat",
    assistantTyping: "L'assistente sta scrivendo",
    messageLabel: "Messaggio",
    loadingHistory: "Caricamento cronologia chat…",
    waitingReply: "In attesa di risposta…",
    typeMessage: "Scrivi un messaggio…",
    send: "Invia",
    sending: "Invio…",
    greeting:
      "Ciao! Sono il receptionist (prototipo). Come posso aiutarti oggi?",
    defaultReply: "Grazie — ho ricevuto il tuo messaggio.",
    sendError: (msg) => `Spiacenti — impossibile inviare il messaggio. ${msg}`,
    footerApiDocs: "Documentazione API backend",
    footerSavedRequests: "Visualizza richieste salvate (JSON)",
    landingAriaLabel: "Benvenuto",
  },
  es: {
    eyebrow: "Recepcionista IA",
    welcome: "Bienvenido",
    landingSubtitle:
      "Su recepcionista con IA está listo para ayudarle con reservas, preguntas y más.",
    languageLabel: "Idioma",
    start: "Empezar",
    appTitle: "Prototipo de recepcionista IA",
    headerEmail: "Introduzca su correo para chatear con nuestro recepcionista.",
    headerChat: (email) =>
      `Chateando como ${email}. Su sesión está guardada en esta pestaña del navegador.`,
    checkingSession: "Comprobando su sesión…",
    beforeWeBegin: "Antes de empezar",
    emailLead:
      "Comparta su correo para enviarle confirmaciones de reserva y actualizaciones.",
    emailLabel: "Correo electrónico",
    emailPlaceholder: "usted@ejemplo.es",
    emailRequired: "Introduzca su correo electrónico.",
    emailInvalid: "Introduzca un correo electrónico válido.",
    sessionStartError: (msg) => `No se pudo iniciar la sesión. ${msg}`,
    continueToChat: "Continuar al chat",
    starting: "Iniciando…",
    chatAriaLabel: "Chat",
    assistantTyping: "El asistente está escribiendo",
    messageLabel: "Mensaje",
    loadingHistory: "Cargando historial del chat…",
    waitingReply: "Esperando respuesta…",
    typeMessage: "Escriba un mensaje…",
    send: "Enviar",
    sending: "Enviando…",
    greeting:
      "¡Hola! Soy el recepcionista (prototipo). ¿En qué puedo ayudarle hoy?",
    defaultReply: "Gracias — he recibido su mensaje.",
    sendError: (msg) => `Lo sentimos — no se pudo enviar el mensaje. ${msg}`,
    footerApiDocs: "Documentación API del backend",
    footerSavedRequests: "Ver solicitudes guardadas (JSON)",
    landingAriaLabel: "Bienvenido",
  },
};

function isNetworkFetchError(message) {
  return /failed to fetch|networkerror|load failed/i.test(message || "");
}

function sessionStartErrorMessage(t, err) {
  const msg = err?.message || "Unknown error";
  if (isNetworkFetchError(msg)) {
    return (
      t.sessionStartNetworkError ||
      "Could not reach the server. Run `docker compose up` and open http://localhost:8080."
    );
  }
  return t.sessionStartError(msg);
}

function getCopy(language) {
  return COPY[language] ?? COPY.en;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithRetry(url, options = {}, retries = 3) {
  let lastError;
  for (let attempt = 1; attempt <= retries; attempt += 1) {
    try {
      const res = await fetch(url, options);
      if (res.status >= 500 && attempt < retries) {
        await sleep(2 ** (attempt - 1) * 500);
        continue;
      }
      return res;
    } catch (err) {
      lastError = err;
      if (attempt < retries) {
        await sleep(2 ** (attempt - 1) * 500);
        continue;
      }
      throw err;
    }
  }
  throw lastError;
}

async function parseApiError(res) {
  const text = await res.text();
  try {
    const data = JSON.parse(text);
    if (data?.error?.message) return data.error.message;
  } catch {
    /* not JSON */
  }
  return text || `HTTP ${res.status}`;
}

function readStoredSessionToken() {
  try {
    const value = sessionStorage.getItem(SESSION_TOKEN_KEY);
    return value && value.trim() ? value.trim() : null;
  } catch {
    return null;
  }
}

function apiHeaders(extra = {}) {
  const headers = { ...extra };
  const token = readStoredSessionToken();
  if (token) headers["X-Session-Token"] = token;
  return headers;
}

function readStoredSessionId() {
  try {
    const value = sessionStorage.getItem(SESSION_STORAGE_KEY);
    return value && value.trim() ? value.trim() : null;
  } catch {
    return null;
  }
}

function readStoredEmail() {
  try {
    const value = sessionStorage.getItem(EMAIL_STORAGE_KEY);
    return value && value.trim() ? value.trim() : null;
  } catch {
    return null;
  }
}

function readStoredLanguage() {
  try {
    const value = sessionStorage.getItem(LANGUAGE_STORAGE_KEY);
    return value && LANGUAGES.some((l) => l.code === value) ? value : "en";
  } catch {
    return "en";
  }
}

function storeLanguage(code) {
  try {
    sessionStorage.setItem(LANGUAGE_STORAGE_KEY, code);
  } catch {
    // ignore
  }
}

function storeSession(sessionId, email, sessionToken) {
  try {
    sessionStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    sessionStorage.setItem(EMAIL_STORAGE_KEY, email);
    if (sessionToken) sessionStorage.setItem(SESSION_TOKEN_KEY, sessionToken);
  } catch {
    // Ignore storage errors (private mode, quota, etc.)
  }
}

function clearStoredSession() {
  try {
    sessionStorage.removeItem(SESSION_STORAGE_KEY);
    sessionStorage.removeItem(SESSION_TOKEN_KEY);
    sessionStorage.removeItem(EMAIL_STORAGE_KEY);
  } catch {
    // ignore
  }
}

function greetingMessage(language) {
  return {
    id: "greeting",
    role: "assistant",
    text: getCopy(language).greeting,
  };
}

function historyToMessages(historyMessages) {
  return historyMessages.map((item) => ({
    id: item.id,
    role: item.role,
    text: item.text,
  }));
}

function isValidEmail(value) {
  return EMAIL_RE.test(value.trim());
}

export default function App() {
  const sessionIdRef = useRef(readStoredSessionId());
  const hasStoredSession = Boolean(sessionIdRef.current);
  const [guestEmail, setGuestEmail] = useState(readStoredEmail() || "");
  const [language, setLanguage] = useState(readStoredLanguage);
  const [showLanding, setShowLanding] = useState(!hasStoredSession);
  const [emailDraft, setEmailDraft] = useState("");
  const [emailError, setEmailError] = useState("");
  const [startingSession, setStartingSession] = useState(false);
  const [sessionReady, setSessionReady] = useState(false);
  const [checkingSession, setCheckingSession] = useState(hasStoredSession);

  const [messages, setMessages] = useState(() => [greetingMessage(readStoredLanguage())]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const listRef = useRef(null);
  const canSend = useMemo(
    () => sessionReady && !sending && !loadingHistory && draft.trim().length > 0,
    [sessionReady, sending, loadingHistory, draft],
  );

  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, sending, loadingHistory]);

  async function loadChatHistory(sessionId) {
    setLoadingHistory(true);
    try {
      const res = await fetchWithRetry(`/api/chat-history/${encodeURIComponent(sessionId)}`, {
        headers: apiHeaders(),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();

      sessionIdRef.current = data.session_id || sessionId;
      if (data.guest_email) {
        setGuestEmail(data.guest_email);
        storeSession(sessionIdRef.current, data.guest_email);
      }

      if (data.messages?.length) {
        setMessages(historyToMessages(data.messages));
      } else {
        setMessages([greetingMessage(language)]);
      }
    } catch {
      clearStoredSession();
      sessionIdRef.current = null;
      setGuestEmail("");
      setSessionReady(false);
      setMessages([greetingMessage(language)]);
    } finally {
      setLoadingHistory(false);
    }
  }

  useEffect(() => {
    const storedSessionId = sessionIdRef.current;
    if (!storedSessionId) {
      setCheckingSession(false);
      return;
    }

    let cancelled = false;

    async function verifySession() {
      try {
        const res = await fetchWithRetry(`/api/session/${encodeURIComponent(storedSessionId)}`, {
          headers: apiHeaders(),
        });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();
        if (cancelled) return;

        sessionIdRef.current = data.session_id;
        setGuestEmail(data.guest_email);
        storeSession(data.session_id, data.guest_email, data.session_token);
        setSessionReady(true);
        await loadChatHistory(data.session_id);
      } catch {
        if (cancelled) return;
        clearStoredSession();
        sessionIdRef.current = null;
        setGuestEmail("");
        setSessionReady(false);
      } finally {
        if (!cancelled) {
          setCheckingSession(false);
        }
      }
    }

    verifySession();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onStartSession(e) {
    e.preventDefault();
    const t = getCopy(language);
    const email = emailDraft.trim().toLowerCase();
    if (!email) {
      setEmailError(t.emailRequired);
      return;
    }
    if (!isValidEmail(email)) {
      setEmailError(t.emailInvalid);
      return;
    }

    setEmailError("");
    setStartingSession(true);

    try {
      const res = await fetchWithRetry("/api/session/start", {
        method: "POST",
        headers: apiHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          email,
          session_id: sessionIdRef.current || undefined,
        }),
      });

      if (!res.ok) {
        throw new Error(await parseApiError(res));
      }

      const data = await res.json();
      sessionIdRef.current = data.session_id;
      storeSession(data.session_id, data.guest_email, data.session_token);
      setGuestEmail(data.guest_email);
      setSessionReady(true);
      setMessages([greetingMessage(language)]);
    } catch (err) {
      setEmailError(sessionStartErrorMessage(t, err));
    } finally {
      setStartingSession(false);
    }
  }

  async function postChat(message, sessionId) {
    const res = await fetchWithRetry("/api/chat", {
      method: "POST",
      headers: apiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        message,
        session_id: sessionId,
        client_message_id: crypto.randomUUID(),
      }),
    });

    if (!res.ok) {
      throw new Error(await parseApiError(res));
    }

    return res.json();
  }

  async function onSubmit(e) {
    e.preventDefault();
    const t = getCopy(language);
    const text = draft.trim();
    if (!text || sending || loadingHistory || !sessionReady || !sessionIdRef.current) return;

    const sessionId = sessionIdRef.current;
    setDraft("");
    setSending(true);

    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "user", text },
    ]);

    try {
      const data = await postChat(text, sessionId);
      if (data?.session_id) {
        sessionIdRef.current = data.session_id;
        storeSession(data.session_id, guestEmail);
      }

      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: data?.reply ?? t.defaultReply,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          kind: "err",
          text: t.sendError(err.message),
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  const t = getCopy(language);
  const showEmailGate = !showLanding && !sessionReady && !checkingSession;

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  function onLanguageChange(code) {
    setLanguage(code);
    storeLanguage(code);
  }

  function onLandingStart() {
    setShowLanding(false);
  }

  return (
    <main className="container">
      {showLanding ? (
        <section className="landing" aria-label={t.landingAriaLabel}>
          <div className="landing-inner">
            <p className="landing-eyebrow">{t.eyebrow}</p>
            <h1 className="landing-title">{t.welcome}</h1>
            <p className="landing-subtitle">{t.landingSubtitle}</p>

            <div className="landing-controls">
              <label className="landing-label" htmlFor="languageSelect">
                {t.languageLabel}
              </label>
              <select
                id="languageSelect"
                className="select"
                value={language}
                onChange={(e) => onLanguageChange(e.target.value)}
              >
                {LANGUAGES.map((lang) => (
                  <option key={lang.code} value={lang.code}>
                    {lang.label}
                  </option>
                ))}
              </select>

              <button className="primary landing-start" type="button" onClick={onLandingStart}>
                {t.start}
              </button>
            </div>
          </div>
        </section>
      ) : (
        <>
      <header className="header">
        <h1>{t.appTitle}</h1>
        <p className="subtitle">
          {sessionReady ? t.headerChat(guestEmail) : t.headerEmail}
        </p>
      </header>

      {checkingSession ? (
        <section className="card prechat">
          <p className="prechat-lead">{t.checkingSession}</p>
        </section>
      ) : null}

      {showEmailGate ? (
        <section className="card prechat">
          <h2 className="prechat-title">{t.beforeWeBegin}</h2>
          <p className="prechat-lead">{t.emailLead}</p>
          <form className="prechat-form" onSubmit={onStartSession} noValidate>
            <label className="sr-only" htmlFor="emailInput">
              {t.emailLabel}
            </label>
            <input
              id="emailInput"
              className="input"
              type="email"
              placeholder={t.emailPlaceholder}
              value={emailDraft}
              onChange={(e) => {
                setEmailDraft(e.target.value);
                if (emailError) setEmailError("");
              }}
              disabled={startingSession}
              autoComplete="email"
              required
            />
            {emailError ? <p className="form-error">{emailError}</p> : null}
            <button className="primary prechat-submit" type="submit" disabled={startingSession}>
              {startingSession ? t.starting : t.continueToChat}
            </button>
          </form>
        </section>
      ) : null}

      {sessionReady ? (
        <section className="card">
          <div className="chat" aria-label={t.chatAriaLabel}>
            <div
              ref={listRef}
              className="messages"
              aria-live="polite"
              aria-relevant="additions"
            >
              {loadingHistory ? (
                <div className="message assistant">
                  <div className="bubble loading" aria-busy="true">
                    <span className="typing-dots">
                      <span />
                      <span />
                      <span />
                    </span>
                  </div>
                </div>
              ) : (
                messages.map((m) => (
                  <div
                    key={m.id}
                    className={`message ${m.role}${m.kind === "err" ? " err" : ""}`}
                  >
                    <div className="bubble">{m.text}</div>
                  </div>
                ))
              )}
              {sending ? (
                <div className="message assistant">
                  <div
                    className="bubble loading"
                    aria-busy="true"
                    aria-label={t.assistantTyping}
                  >
                    <span className="typing-dots">
                      <span />
                      <span />
                      <span />
                    </span>
                  </div>
                </div>
              ) : null}
            </div>

            <form className="composer" onSubmit={onSubmit} autoComplete="off">
              <label className="sr-only" htmlFor="messageInput">
                {t.messageLabel}
              </label>
              <input
                id="messageInput"
                className="input"
                type="text"
                placeholder={
                  loadingHistory
                    ? t.loadingHistory
                    : sending
                      ? t.waitingReply
                      : t.typeMessage
                }
                maxLength={2000}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                disabled={sending || loadingHistory}
                required
              />
              <button className="primary" type="submit" disabled={!canSend}>
                {sending ? t.sending : t.send}
              </button>
            </form>
          </div>
        </section>
      ) : null}

      <footer className="footer">
        <a href="/docs" target="_blank" rel="noreferrer">
          {t.footerApiDocs}
        </a>
      </footer>
        </>
      )}
    </main>
  );
}

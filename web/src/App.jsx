import { useEffect, useRef, useState } from "react";
import { signInWithGoogle, signOutFirebase, getStoredSession, getIdToken } from "./firebase";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const API_ORIGIN = new URL(API_BASE).origin;

function clampText(text, maxLength) {
  const value = String(text || "").trim();
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength - 3).trim()}...`;
}

function renderTextWithLinks(text) {
  const value = String(text || "");
  if (!value) return null;
  const pattern = /(https?:\/\/[^\s)]+|mailto:[^\s)]+)/g;
  const parts = value.split(pattern);
  return parts.map((part, index) => {
    const isLink = part.startsWith("http") || part.startsWith("mailto:");
    if (isLink) {
      return (
        <a key={`link-${index}`} href={part} target="_blank" rel="noopener noreferrer">{part}</a>
      );
    }
    return <span key={`text-${index}`}>{part}</span>;
  });
}

function renderBullets(items, emptyLabel) {
  if (!items || items.length === 0) {
    return <p className="meta">{emptyLabel}</p>;
  }
  return (
    <ul>
      {items.map((item, idx) => (
        <li key={`bullet-${idx}`}>{renderTextWithLinks(item)}</li>
      ))}
    </ul>
  );
}

function renderSummary(text) {
  const value = String(text || "");
  if (!value) return null;
  const lines = value.split("\n");
  const elements = [];
  let inBullets = false;
  let bulletItems = [];
  let titleRendered = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed.startsWith("- ")) {
      inBullets = true;
      bulletItems.push(trimmed.slice(2));
      continue;
    }

    if (inBullets) {
      elements.push(
        <ul key={`bullets-${elements.length}`} className="summary-bullets">
          {bulletItems.map((item, idx) => (
            <li key={`sb-${idx}`}>{renderTextWithLinks(item)}</li>
          ))}
        </ul>
      );
      bulletItems = [];
      inBullets = false;
    }

    if (!trimmed) {
      elements.push(<div key={`spacer-${i}`} className="summary-spacer" />);
      continue;
    }

    const lower = trimmed.toLowerCase();

    if (!titleRendered && (lower.includes("simple summary") || lower.includes("summary of"))) {
      elements.push(
        <h3 key={`title-${i}`} className="summary-title">{renderTextWithLinks(trimmed)}</h3>
      );
      titleRendered = true;
      continue;
    }

    if (lower.startsWith("overall:")) {
      const rest = trimmed.slice("overall:".length).trim();
      elements.push(
        <p key={`overall-${i}`} className="summary-overall">
          <strong>Overall:</strong> {renderTextWithLinks(rest)}
        </p>
      );
      continue;
    }

    if (trimmed.endsWith(":") && trimmed.length < 40) {
      elements.push(
        <p key={`heading-${i}`} className="summary-subheading">{renderTextWithLinks(trimmed)}</p>
      );
      continue;
    }

    elements.push(
      <p key={`line-${i}`} className="summary-line">{renderTextWithLinks(trimmed)}</p>
    );
  }

  if (inBullets) {
    elements.push(
      <ul key={`bullets-end`} className="summary-bullets">
        {bulletItems.map((item, idx) => (
          <li key={`sb-${idx}`}>{renderTextWithLinks(item)}</li>
        ))}
      </ul>
    );
  }

  return elements;
}

function formatBytes(value) {
  const size = Number(value || 0);
  if (!size) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let index = 0;
  let current = size;
  while (current >= 1024 && index < units.length - 1) {
    current /= 1024;
    index += 1;
  }
  return `${current.toFixed(current < 10 && index > 0 ? 1 : 0)} ${units[index]}`;
}

function buildAttachmentUrl(messageId, attachment) {
  if (!messageId || !attachment) return "";
  if (attachment.attachment_id) {
    return `${API_BASE}/api/messages/${messageId}/attachments/${attachment.attachment_id}`;
  }
  if (attachment.part_id) {
    return `${API_BASE}/api/messages/${messageId}/attachments/part/${attachment.part_id}`;
  }
  return "";
}

function replaceCidImages(html, attachments, messageId) {
  const value = String(html || "");
  if (!value || !attachments || attachments.length === 0) return value;
  const cidMap = new Map();
  attachments.forEach((attachment) => {
    const contentId = String(attachment.content_id || "").replace(/^<|>$/g, "").toLowerCase();
    if (!contentId) return;
    const url = buildAttachmentUrl(messageId, attachment);
    if (url) cidMap.set(contentId, url);
  });
  if (cidMap.size === 0) return value;
  return value.replace(/src=["']cid:([^"']+)["']/gi, (match, cid) => {
    const key = String(cid || "").replace(/^<|>$/g, "").toLowerCase();
    const url = cidMap.get(key);
    if (!url) return match;
    return `src="${url}"`;
  });
}

function buildHtmlDocument(html) {
  const body = String(html || "");
  const baseTag = "<base target=\"_blank\" />";
  const styleTag = `<style>body{margin:0;font-family:Arial,sans-serif;font-size:14px;line-height:1.5;color:#1b1a13;background:#fff!important}img{max-width:100%;height:auto}table{max-width:100%;width:100%}</style>`;
  const cspTag = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${API_ORIGIN} https: http: data:; style-src 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; base-uri 'none'; form-action 'none'; object-src 'none'; script-src 'none'; connect-src 'none'; frame-src 'none'" />`;

  if (/<html[\s>]/i.test(body)) {
    if (/<head[\s>]/i.test(body)) {
      return body.replace(/<head[^>]*>/i, (m) => `${m}${cspTag}${baseTag}${styleTag}`);
    }
    return body.replace(/<html[^>]*>/i, (m) => `${m}<head>${cspTag}${baseTag}${styleTag}</head>`);
  }
  return `<!doctype html><html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>${cspTag}${baseTag}${styleTag}</head><body>${body}</body></html>`;
}

function IconSpark() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z" />
      <path d="M12 15v6" />
      <path d="M8 18h8" />
    </svg>
  );
}

function IconExternal() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  );
}

function IconMail() {
  return (
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <polyline points="22,7 12,13 2,7" />
    </svg>
  );
}

function LoadingScreen() {
  return (
    <div className="landing">
      <div className="landing-hero">
        <div className="landing-card">
          <p className="eyebrow">Aegis Mail</p>
          <h1>Loading secure session...</h1>
          <p>Checking your authenticated inbox state.</p>
        </div>
      </div>
    </div>
  );
}

function LandingPage({ onSignIn, signInError }) {
  return (
    <div className="landing">
      <nav className="landing-nav">
        <div className="landing-brand">
          <img src="/logo2.png" alt="Aegis Mail" className="landing-logo" />
          Aegis Mail
        </div>
        <div className="landing-nav-actions">
          <button className="btn primary" onClick={onSignIn}>Sign in with Google</button>
        </div>
      </nav>
      <section className="landing-hero">
        <div className="landing-card">
          <p className="eyebrow"><IconSpark /> AI-powered inbox</p>
          <h1>Read, understand, and <span className="highlight">act</span> on email faster.</h1>
          <p>Summarizes your Gmail with AI — explains the context, jargon, and what you need to do, in plain language.</p>
          {signInError && <p className="error" style={{marginTop: '1rem'}}>{signInError}</p>}
          <div className="landing-cta">
            <button className="btn primary" onClick={onSignIn}>Continue with Google</button>
          </div>
        </div>
      </section>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState("");
  const [sessionReady, setSessionReady] = useState(false);
  const [signInError, setSignInError] = useState("");
  const [idToken, setIdToken] = useState("");
  const idTokenRef = useRef("");
  const [needGmail, setNeedGmail] = useState(false);
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [showInsight, setShowInsight] = useState(false);
  const [insightLoading, setInsightLoading] = useState(false);
  const [showFullBody, setShowFullBody] = useState(false);
  const [attachmentPreviewId, setAttachmentPreviewId] = useState("");
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [maxResults, setMaxResults] = useState(20);
  const [fontScale, setFontScale] = useState(() => {
    const saved = localStorage.getItem("aegis-font-scale");
    return saved ? parseFloat(saved) : 1;
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showSettings, setShowSettings] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deletingAccount, setDeletingAccount] = useState(false);

  useEffect(() => {
    if (window.location.pathname === "/auth/callback") {
      window.history.replaceState({}, "", "/");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function initSession() {
      const stored = getStoredSession();
      if (!stored.uid) {
        if (!cancelled) setSessionReady(true);
        return;
      }
      const freshToken = await getIdToken();
      if (freshToken) {
        setIdToken(freshToken);
        idTokenRef.current = freshToken;
      }
      try {
        const headers = { "Content-Type": "application/json" };
        if (freshToken) headers["Authorization"] = `Bearer ${freshToken}`;
        const response = await fetch(`${API_BASE}/api/me`, { credentials: "include", headers });
        if (!response.ok) { if (!cancelled) setUser(""); return; }
        const data = await response.json();
        if (!cancelled) setUser(String(data.user || ""));
      } catch { if (!cancelled) setUser(""); }
      finally { if (!cancelled) setSessionReady(true); }
    }
    initSession();
    return () => { cancelled = true; };
  }, []);

  async function handleSignIn() {
    try {
      setSignInError("");
      const { idToken: token } = await signInWithGoogle();
      setIdToken(token);
      idTokenRef.current = token;
      const response = await fetch(`${API_BASE}/api/auth/firebase`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ id_token: token }),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Auth error ${response.status}`);
      }
      const data = await response.json();
      setUser(String(data.user || ""));
      setSessionReady(true);
    } catch (err) {
      const msg = err._friendlyMessage || String(err);
      setSignInError(msg);
    }
  }

  function authFetch(path, options = {}) {
    const headers = { ...options.headers };
    const token = idTokenRef.current;
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return fetch(`${API_BASE}${path}`, { ...options, credentials: "include", headers });
  }

  async function fetchMessages() {
    if (!user) return;
    setLoading(true); setError(""); setNeedGmail(false);
    try {
      const params = new URLSearchParams();
      params.set("max_results", String(maxResults));
      if (query.trim()) params.set("query", query.trim());
      const response = await authFetch(`/api/messages?${params}`);
      if (response.status === 401) {
        const errData = await response.json().catch(() => ({}));
        if (errData.detail === "No token for user.") { setNeedGmail(true); return; }
        throw new Error(`API error ${response.status}`);
      }
      if (!response.ok) throw new Error(`API error ${response.status}`);
      const data = await response.json();
      const nextItems = data.items || [];
      setItems(nextItems);
      setSelected(prev => prev ? nextItems.find(i => i.id === prev.id) : null);
    } catch (err) { setError(String(err)); }
    finally { setLoading(false); }
  }

  function connectGmail() {
    window.location.href = `${API_BASE}/auth/google`;
  }

  async function logout() {
    await signOutFirebase().catch(() => {});
    setIdToken(""); setNeedGmail(false);
    authFetch("/auth/logout").finally(() => {
      setUser(""); setItems([]); setSelected(null); setLoading(false); setError("");
      setShowInsight(false); setShowFullBody(false); setAttachmentPreviewId("");
      setSummaryLoading(false); setSessionReady(true);
      setSearchInput(""); setQuery("");
    });
  }

  async function handleDeleteAccount() {
    setDeletingAccount(true);
    try {
      const response = await authFetch("/api/auth/delete-account", { method: "POST" });
      if (!response.ok) throw new Error(`Delete failed (${response.status})`);
      await signOutFirebase().catch(() => {});
      setIdToken(""); setUser(""); setItems([]); setSelected(null); setLoading(false);
      setSessionReady(true); setShowSettings(false); setDeleteConfirm(false);
    } catch (err) {
      setError(String(err));
    } finally {
      setDeletingAccount(false);
    }
  }

  useEffect(() => {
    localStorage.setItem("aegis-font-scale", String(fontScale));
  }, [fontScale]);

  useEffect(() => { if (user) fetchMessages(); }, [user, query, maxResults]);

  useEffect(() => {
    const timer = setTimeout(() => setQuery(searchInput), 350);
    return () => clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    setShowInsight(false); setShowFullBody(false); setAttachmentPreviewId("");
  }, [selected?.id]);

  useEffect(() => {
    if (!selected || !user) return undefined;
    if (selected.provider === "gemini") return undefined;
    let cancelled = false;
    async function fetchSummary() {
      setSummaryLoading(true);
      try {
        const response = await authFetch(`/api/messages/${selected.id}/summary`);
        if (!response.ok) throw new Error(`Summary error ${response.status}`);
        const data = await response.json();
        if (cancelled) return;
        setSelected(prev => prev ? { ...prev, ...data } : prev);
        setItems(prev => prev.map(item => item.id === selected.id ? { ...item, ...data } : item));
      } catch (err) { if (!cancelled) setError(String(err)); }
      finally { if (!cancelled) setSummaryLoading(false); }
    }
    fetchSummary();
    return () => { cancelled = true; };
  }, [selected?.id, user]);

  useEffect(() => {
    if (!showInsight) return undefined;
    setInsightLoading(true);
    const timer = setTimeout(() => setInsightLoading(false), 900);
    return () => clearTimeout(timer);
  }, [showInsight, selected?.id]);

  if (!sessionReady) return <LoadingScreen />;
  if (!user) return <LandingPage onSignIn={handleSignIn} signInError={signInError} />;

  const userInitial = (user || "U")[0].toUpperCase();

  function MsgCard({ item }) {
    return (
      <button
        className={`msg-card ${selected?.id === item.id ? "active" : ""} ${item.is_unread ? "unread" : ""}`}
        onClick={() => setSelected(item)}
      >
        <div className="msg-card-top">
          <span className="msg-sender">{item.from_name || item.from?.split("<")[0]?.trim() || item.from || "Unknown"}</span>
          <span className="msg-date">{item.date}</span>
        </div>
        <div className="msg-card-subj-row">
          {item.is_unread && <span className="msg-unread" />}
          <p className="msg-subject">{item.subject || "(no subject)"}</p>
        </div>
        <p className="msg-preview">{clampText(item.summary || item.snippet, 160)}</p>
        <div className="msg-card-footer">
          <div className="msg-tags">
            <span className="msg-tag">{item.topic || "General"}</span>
            {(item.attachments || []).length > 0 && (
              <span className="msg-tag">{(item.attachments || []).length} files</span>
            )}
          </div>
        </div>
      </button>
    );
  }

  return (
    <div className="app" style={{ zoom: fontScale }}>
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <img src="/logo2.png" alt="Aegis" className="sidebar-logo-img" />
          <span className="sidebar-title">Aegis</span>
          <button className="sidebar-settings-btn" onClick={() => setShowSettings(true)} title="Settings">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </button>
        </div>
        <div className="sidebar-search">
          <svg className="sidebar-search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input placeholder="Search inbox…" value={searchInput} onChange={e => setSearchInput(e.target.value)} />
        </div>
        <div className="sidebar-list">
          <div className="sidebar-list-header">
            <span>Inbox</span>
            <span>{loading ? "…" : items.length}</span>
          </div>
          {needGmail && (
            <div style={{padding: '16px 10px', textAlign: 'center'}}>
              <p style={{fontSize: '13px', color: 'rgba(255,255,255,0.5)', margin: '0 0 10px'}}>Connect Gmail to read your inbox</p>
              <button className="btn primary" onClick={connectGmail}>Connect Gmail</button>
            </div>
          )}
          {loading && items.length === 0 && (
            <div className="skeleton-stack">
              <div className="msg-skeleton" /><div className="msg-skeleton" />
              <div className="msg-skeleton" /><div className="msg-skeleton" />
            </div>
          )}
          {items.length === 0 && !loading && (
            <div style={{padding: '24px 10px', textAlign: 'center', color: 'rgba(255,255,255,0.25)', fontSize: '13px'}}>
              No messages found.
            </div>
          )}
          {loading && items.length > 0 && <div className="search-loader" />}
          {items.map(item => <MsgCard key={item.id} item={item} />)}
        </div>
        <div className="sidebar-footer">
          <div className="user-chip">
            <div className="user-avatar">{userInitial}</div>
            <span className="user-name">{user}</span>
          </div>
          <button className="btn ghost small" onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="main-content">
        <div className="main-topbar">
          <div className="main-topbar-left">
            {!selected && <h2>Inbox</h2>}
          </div>
          <div className="main-topbar-right">
            <div className="limit-group">
              <span className="limit-label">Limit</span>
              <button className="limit-btn" onClick={() => setMaxResults(p => Math.max(1, p - 1))}>−</button>
              <span className="limit-value">{maxResults}</span>
              <button className="limit-btn" onClick={() => setMaxResults(p => Math.min(100, p + 1))}>+</button>
            </div>
            <div className="limit-group" style={{marginLeft: '4px'}}>
              <span className="limit-label">A</span>
              <button className="limit-btn" onClick={() => setFontScale(p => Math.max(0.8, +(p - 0.1).toFixed(1)))}>−</button>
              <span className="limit-value">{Math.round(fontScale * 100)}%</span>
              <button className="limit-btn" onClick={() => setFontScale(p => Math.min(1.4, +(p + 0.1).toFixed(1)))}>+</button>
            </div>
            <button className="btn" onClick={fetchMessages} disabled={!user || loading}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
              </svg>
              {loading ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        </div>

        {error && <div style={{padding: '10px 24px'}}><p className="error">{error}</p></div>}

        {selected ? (
          <div className="detail-view">
            <div className="detail-header">
              <h2>{selected.subject}</h2>
              <div className="detail-header-meta">
                <span>From: {selected.from}</span>
                <span>To: {selected.to}</span>
                <span>{selected.date}</span>
              </div>
              <div className="detail-header-actions">
                <button className="btn icon-btn" onClick={() => setShowInsight(true)} title="AI Insights"><IconSpark /></button>
                {selected.gmail_url && (
                  <a className="btn icon-btn" href={selected.gmail_url} target="_blank" rel="noopener noreferrer" title="Open in Gmail"><IconExternal /></a>
                )}
                <button className="btn" onClick={() => setSelected(null)}>Close</button>
              </div>
            </div>
            <div className="detail-scroll">
              {/* AI Summary Hero */}
              <div className="summary-hero">
                <div className="summary-hero-header">
                  <IconSpark />
                  <h3>AI Summary</h3>
                  <span className={`pill pill-${selected.category || "informational"}`}>
                    {selected.category || "informational"}
                  </span>
                  <span className="pill">{selected.topic || "General"}</span>
                </div>
                {summaryLoading ? (
                  <div>
                    <div className="live-indicator"><span className="live-dot" /> Generating summary</div>
                    <div className="insight-skeleton" style={{marginTop: '10px'}}>
                      <div className="skeleton-line w-90" /><div className="skeleton-line w-75" />
                      <div className="skeleton-line w-80" /><div className="skeleton-line w-60" />
                    </div>
                  </div>
                ) : (
                  <div className="summary-content">
                    {renderSummary(selected.summary || selected.snippet || "No summary available.")}
                    {(selected.action_items || []).length > 0 && (
                      <>
                        <p className="insight-label">What to do</p>
                        {renderBullets(selected.action_items)}
                      </>
                    )}
                  </div>
                )}
              </div>

              {/* Sender */}
              <div className="detail-section">
                <h4>Sender</h4>
                <div className="sender-grid">
                  <div><p className="sender-label">Name</p><p>{selected.from_name || "Unknown"}</p></div>
                  <div><p className="sender-label">Email</p><p>{selected.from_email || "Unknown"}</p></div>
                  <div><p className="sender-label">To</p><p>{(selected.to_emails || []).join(", ") || selected.to}</p></div>
                </div>
              </div>

              {/* Unsubscribe */}
              <div className="detail-section">
                <h4>Unsubscribe</h4>
                <p>{selected.unsubscribe_instructions || "Not available"}</p>
                {(selected.list_unsubscribe || []).length > 0 && (
                  <div style={{marginTop: '6px', display: 'flex', flexDirection: 'column', gap: '3px'}}>
                    {selected.list_unsubscribe.map(item => {
                      const isLink = item.startsWith("http") || item.startsWith("mailto:");
                      return isLink
                        ? <a key={item} className="link" href={item} target="_blank" rel="noopener noreferrer">{item}</a>
                        : <span key={item} className="meta">{item}</span>;
                    })}
                  </div>
                )}
              </div>

              {/* Attachments */}
              {(selected.attachments || []).length > 0 && (
                <div className="detail-section">
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px'}}>
                    <h4 style={{margin: 0}}>Attachments</h4>
                    <span className="meta">{(selected.attachments || []).length} files</span>
                  </div>
                  <div style={{display: 'flex', flexDirection: 'column', gap: '6px'}}>
                    {(selected.attachments || []).map((att, idx) => {
                      const key = att.attachment_id || att.part_id || `${idx}`;
                      const url = buildAttachmentUrl(selected.id, att);
                      const isPdf = String(att.mime_type || "").toLowerCase() === "application/pdf";
                      return (
                        <div key={`${selected.id}-att-${key}`}>
                          <div className="attachment-item">
                            <div className="attachment-icon">
                              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                                <polyline points="14 2 14 8 20 8" />
                              </svg>
                            </div>
                            <div className="attachment-info">
                              <div className="attachment-name">{att.filename || "Attachment"}</div>
                              <div className="attachment-meta">{att.mime_type || "application/octet-stream"} — {formatBytes(att.size)}</div>
                            </div>
                            <div className="attachment-actions">
                              {isPdf && url && (
                                <button className="link" onClick={() => setAttachmentPreviewId(prev => prev === key ? "" : key)}>
                                  {attachmentPreviewId === key ? "Hide" : "Preview"}
                                </button>
                              )}
                              {url && <><a className="link" href={url} target="_blank" rel="noopener noreferrer">Open</a><a className="link" href={url} download>Download</a></>}
                            </div>
                          </div>
                          {isPdf && url && attachmentPreviewId === key && (
                            <iframe className="attachment-preview" title={`Preview ${att.filename || "attachment"}`} src={url} />
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Message body */}
              <div className="detail-section">
                <h4>Message</h4>
                {selected.body_html ? (
                  <iframe className="mail-html-frame" title="Email HTML preview" sandbox="allow-popups" referrerPolicy="no-referrer"
                    srcDoc={buildHtmlDocument(replaceCidImages(selected.body_html, selected.attachments || [], selected.id))} />
                ) : (
                  <>
                    <div className={`mail-body ${showFullBody ? "expanded" : ""}`}>
                      {renderTextWithLinks(selected.body || "No body available.")}
                    </div>
                    {selected.body && selected.body.length > 200 && (
                      <button className="link" style={{marginTop: '6px'}} onClick={() => setShowFullBody(p => !p)}>
                        {showFullBody ? "Show less" : "Show more"}
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="detail-view empty">
            <div className="empty-detail">
              <IconMail />
              <h3>Select a message</h3>
              <p>Choose an email from your inbox to view its AI summary, details, and more.</p>
            </div>
          </div>
        )}
      </div>

      {/* Modal */}
      {showInsight && selected && (
        <div className="modal-backdrop" onClick={() => setShowInsight(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <p className="modal-label">{insightLoading ? <span className="live-indicator"><span className="live-dot" /> Summarizing</span> : "AI Insights"}</p>
                <h3>{selected.subject}</h3>
              </div>
              <button className="btn ghost" onClick={() => setShowInsight(false)}>Close</button>
            </div>
            {insightLoading ? (
              <div className="insight-skeleton">
                <div className="skeleton-line w-60" /><div className="skeleton-line w-90" />
                <div className="skeleton-line w-75" /><div className="skeleton-line w-80" />
              </div>
            ) : (
              <div className="modal-grid">
                <div>
                  <p className="modal-label">Summary</p>
                  <div className="summary-rich">{renderSummary(selected.summary || selected.snippet || "No summary available.")}</div>
                  {(selected.action_items || []).length > 0 && (
                    <><p className="modal-label" style={{marginTop: '12px'}}>What to do</p>{renderBullets(selected.action_items)}</>
                  )}
                </div>
                <div>
                  <p className="modal-label">Topic</p>
                  <p>{selected.topic || "General"}</p>
                  <p className="modal-label" style={{marginTop: '10px'}}>Category</p>
                  <span className={`pill pill-${selected.category || "informational"}`}>{selected.category || "informational"}</span>
                  <p className="modal-label" style={{marginTop: '10px'}}>Unsubscribe</p>
                  <p>{selected.unsubscribe_instructions || "Not available"}</p>
                  {(selected.list_unsubscribe || []).length > 0 && (
                    <div style={{marginTop: '4px', display: 'flex', flexDirection: 'column', gap: '3px'}}>
                      {selected.list_unsubscribe.map(item => {
                        const isLink = item.startsWith("http") || item.startsWith("mailto:");
                        return isLink
                          ? <a key={item} className="link" href={item} target="_blank" rel="noopener noreferrer">{item}</a>
                          : <span key={item} className="meta">{item}</span>;
                      })}
                    </div>
                  )}
                </div>
              </div>
            )}
            <div className="modal-footer">
              <span className="meta">Model: {selected.provider}</span>
            </div>
          </div>
        </div>
      )}

      {/* Settings */}
      {showSettings && (
        <div className="modal-backdrop" onClick={() => { setShowSettings(false); setDeleteConfirm(false); }}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{maxWidth: '440px'}}>
            <div className="modal-header">
              <h3>Settings</h3>
              <button className="btn ghost" onClick={() => { setShowSettings(false); setDeleteConfirm(false); }}>Close</button>
            </div>
            <div className="modal-grid">
              {!deleteConfirm ? (
                <div className="settings-section">
                  <div className="settings-section-header">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
                      <circle cx="9" cy="7" r="4" />
                      <line x1="17" y1="8" x2="23" y2="8" />
                      <line x1="20" y1="5" x2="20" y2="11" />
                    </svg>
                    <div>
                      <p className="settings-section-title">Account</p>
                      <p className="settings-section-desc">Manage your account and connected services</p>
                    </div>
                  </div>
                  <div className="settings-action">
                    <div>
                      <p className="settings-action-title">Delete account</p>
                      <p className="settings-action-desc">Permanently remove your data from our storage and revoke Gmail access.</p>
                    </div>
                    <button className="btn danger" onClick={() => setDeleteConfirm(true)}>Delete</button>
                  </div>
                </div>
              ) : (
                <div className="settings-section">
                  <div className="settings-confirm">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--red)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10" />
                      <line x1="12" y1="8" x2="12" y2="12" />
                      <line x1="12" y1="16" x2="12.01" y2="16" />
                    </svg>
                    <h4>Delete your account?</h4>
                    <p>This will permanently remove your data, revoke Gmail access, and sign you out. This action cannot be undone.</p>
                    <div className="settings-confirm-actions">
                      <button className="btn" onClick={() => setDeleteConfirm(false)} disabled={deletingAccount}>Cancel</button>
                      <button className="btn danger" onClick={handleDeleteAccount} disabled={deletingAccount}>
                        {deletingAccount ? (
                          <><span className="live-dot" /> Deleting…</>
                        ) : (
                          "Yes, delete my account"
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
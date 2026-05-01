import { useEffect, useMemo, useState } from "react";

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
        <a
          key={`link-${index}`}
          href={part}
          target="_blank"
          rel="noopener noreferrer"
        >
          {part}
        </a>
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
    const contentId = String(attachment.content_id || "")
      .replace(/^<|>$/g, "")
      .toLowerCase();
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
  const styleTag = `<style>
      body { margin: 0; font-family: Arial, sans-serif; font-size: 14px; line-height: 1.5; color: #1b1a13; background: #ffffff !important; }
      img { max-width: 100%; height: auto; }
      table { max-width: 100%; width: 100%; }
    </style>`;
    const cspTag = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${API_ORIGIN} https: http: data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; object-src 'none'; script-src 'none'; connect-src 'none'; frame-src 'none'" />`;

  if (/<html[\s>]/i.test(body)) {
    if (/<head[\s>]/i.test(body)) {
      return body.replace(
        /<head[^>]*>/i,
        (match) => `${match}${cspTag}${baseTag}${styleTag}`
      );
    }
    return body.replace(
      /<html[^>]*>/i,
      (match) => `${match}<head>${cspTag}${baseTag}${styleTag}</head>`
    );
  }

  return `<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    ${cspTag}
    ${baseTag}
    ${styleTag}
  </head>
  <body>${body}</body>
</html>`;
}

function IconSpark() {
  return (
    <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M12 2l2.2 6.2L20 10l-5.8 1.8L12 18l-2.2-6.2L4 10l5.8-1.8L12 2z"
        fill="currentColor"
      />
    </svg>
  );
}

function IconExternal() {
  return (
    <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M14 3h7v7h-2V6.4l-8.3 8.3-1.4-1.4 8.3-8.3H14V3z"
        fill="currentColor"
      />
      <path
        d="M5 5h6v2H7v10h10v-4h2v6H5V5z"
        fill="currentColor"
      />
    </svg>
  );
}

function LandingPage({ loginUrl }) {
  return (
    <div className="landing">
      <header className="landing-topbar">
        <div className="brand-mark">Mail AI Manager</div>
        <div className="landing-actions">
          <a className="btn ghost" href="#features">
            Features
          </a>
          <a className="btn primary" href={loginUrl}>
            Continue with Google
          </a>
        </div>
      </header>

      <section className="landing-hero compact">
        <div className="landing-copy compact">
          <p className="eyebrow">AI inbox workspace</p>
          <h1>Read, understand, and act on email faster.</h1>
          <p className="landing-text">
            A modern Gmail-connected service that summarizes emails, highlights attachments, and turns inbox noise into clean action items.
          </p>
          <div className="landing-cta">
            <a className="btn primary" href={loginUrl}>
              Sign in with Google
            </a>
            <a className="btn ghost" href="#features">
              See how it works
            </a>
          </div>
        </div>
      </section>

      <section className="feature-grid" id="features">
        <article className="feature-card">
          <div className="feature-icon">01</div>
          <h3>Google login first</h3>
          <p>Users land on a marketing page and only enter the inbox after authenticating with Google.</p>
        </article>
        <article className="feature-card">
          <div className="feature-icon">02</div>
          <h3>Modern email reading</h3>
          <p>Messages open with smooth transitions, clean spacing, and inline HTML rendering like a premium mail app.</p>
        </article>
        <article className="feature-card">
          <div className="feature-icon">03</div>
          <h3>AI with structure</h3>
          <p>Summaries are split into what it is, main offer, benefits, and next steps so the result is easy to scan.</p>
        </article>
      </section>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState("");
  const [sessionReady, setSessionReady] = useState(false);
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [showInsight, setShowInsight] = useState(false);
  const [insightLoading, setInsightLoading] = useState(false);
  const [showFullBody, setShowFullBody] = useState(false);
  const [attachmentPreviewId, setAttachmentPreviewId] = useState("");
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [maxResults, setMaxResults] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (window.location.pathname === "/auth/callback") {
      window.history.replaceState({}, "", "/");
    }
  }, []);

  const loginUrl = useMemo(() => `${API_BASE}/auth/google`, []);
  const visibleCount = items.length;

  useEffect(() => {
    let cancelled = false;

    async function fetchSession() {
      try {
        const response = await fetch(`${API_BASE}/api/me`, {
          credentials: "include",
        });
        if (!response.ok) {
          if (!cancelled) setUser("");
          return;
        }
        const data = await response.json();
        if (!cancelled) {
          setUser(String(data.user || ""));
        }
      } catch {
        if (!cancelled) setUser("");
      } finally {
        if (!cancelled) setSessionReady(true);
      }
    }

    fetchSession();
    return () => {
      cancelled = true;
    };
  }, []);

  async function fetchMessages() {
    if (!user) return;
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("max_results", String(maxResults));
      if (query.trim()) params.set("query", query.trim());

      const response = await fetch(`${API_BASE}/api/messages?${params}`, {
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error(`API error ${response.status}`);
      }
      const data = await response.json();
      const nextItems = data.items || [];
      setItems(nextItems);
      const nextSelected = selected
        ? nextItems.find((item) => item.id === selected.id)
        : null;
      setSelected(nextSelected || null);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    fetch(`${API_BASE}/auth/logout`, { credentials: "include" }).finally(() => {
      setUser("");
      setItems([]);
      setSelected(null);
      setLoading(false);
      setError("");
      setShowInsight(false);
      setShowFullBody(false);
      setAttachmentPreviewId("");
      setSummaryLoading(false);
      setSessionReady(true);
    });
  }

  useEffect(() => {
    if (user) {
      fetchMessages();
    }
  }, [user, query, maxResults]);

  useEffect(() => {
    setShowInsight(false);
    setShowFullBody(false);
    setAttachmentPreviewId("");
  }, [selected?.id]);

  useEffect(() => {
    if (!selected || !user) return undefined;
    if (selected.provider === "gemini") return undefined;
    let cancelled = false;

    async function fetchSummary() {
      setSummaryLoading(true);
      try {
        const response = await fetch(
          `${API_BASE}/api/messages/${selected.id}/summary`,
          { credentials: "include" }
        );
        if (!response.ok) {
          throw new Error(`Summary error ${response.status}`);
        }
        const data = await response.json();
        if (cancelled) return;
        setSelected((prev) => (prev ? { ...prev, ...data } : prev));
        setItems((prev) =>
          prev.map((item) =>
            item.id === selected.id ? { ...item, ...data } : item
          )
        );
      } catch (err) {
        if (!cancelled) {
          setError(String(err));
        }
      } finally {
        if (!cancelled) {
          setSummaryLoading(false);
        }
      }
    }

    fetchSummary();
    return () => {
      cancelled = true;
    };
  }, [selected?.id, user]);

  useEffect(() => {
    if (!showInsight) return undefined;
    setInsightLoading(true);
    const timer = setTimeout(() => setInsightLoading(false), 900);
    return () => clearTimeout(timer);
  }, [showInsight, selected?.id]);

  if (!sessionReady) {
    return (
      <div className="landing">
        <section className="landing-hero compact">
          <div className="landing-copy compact">
            <p className="eyebrow">Mail AI Manager</p>
            <h1>Loading secure session...</h1>
            <p className="landing-text">Checking your authenticated inbox state.</p>
          </div>
        </section>
      </div>
    );
  }

  if (!user) {
    return <LandingPage loginUrl={loginUrl} />;
  }

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <p className="eyebrow">Mail AI Manager</p>
          <h1>Inbox intelligence, not inbox chaos.</h1>
          <p className="lede">
            Scan unread and read messages, get summaries, and spot action items
            fast.
          </p>
        </div>
        <div className="topbar-actions">
          {user ? (
            <>
              <span className="chip">{user}</span>
              <button className="btn ghost" onClick={logout}>
                Sign out
              </button>
            </>
          ) : (
            <a className="btn primary" href={loginUrl}>
              Sign in with Google
            </a>
          )}
        </div>
      </header>

      <section className="controls">
        <label className="control">
          <span>Search</span>
          <input
            placeholder="from:groww subject:invoice"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={!user}
          />
        </label>
        <label className="control">
          <span>Max</span>
          <input
            type="number"
            min="1"
            max="100"
            value={maxResults}
            onChange={(e) => setMaxResults(Number(e.target.value || 1))}
            disabled={!user}
          />
        </label>
        <button className="btn" onClick={fetchMessages} disabled={!user || loading}>
          {loading ? "Loading..." : "Refresh"}
        </button>
      </section>

      {error && <div className="error">Error: {error}</div>}

      <main className={`grid ${selected ? "has-detail" : "list-only"}`}>
        <section className={`panel list ${selected ? "" : "centered"}`}>
          <div className="panel-head">
            <div>
              <div className="panel-title">Messages</div>
              <h3>Inbox</h3>
            </div>
            <span className="panel-pill">{loading ? "Refreshing" : `${visibleCount} loaded`}</span>
          </div>
          {!user && (
            <div className="empty empty-card">
              <h4>Sign in to open your inbox</h4>
              <p>Use Google authentication to connect your mailbox and start analyzing mail immediately.</p>
              <a className="btn primary" href={loginUrl}>Connect Gmail</a>
            </div>
          )}
          {user && loading && items.length === 0 && (
            <div className="skeleton-stack">
              <div className="message-skeleton" />
              <div className="message-skeleton" />
              <div className="message-skeleton" />
              <div className="message-skeleton" />
            </div>
          )}
          {user && items.length === 0 && !loading && (
            <div className="empty empty-card">No messages found.</div>
          )}
          {items.map((item) => (
            <button
              key={item.id}
              className={`card ${selected?.id === item.id ? "active" : ""}`}
              onClick={() => setSelected(item)}
            >
              <div className="card-head">
                <span className={`badge ${item.is_unread ? "alert" : ""}`}>
                  {item.is_unread ? "Unread" : "Read"}
                </span>
                <span className="meta">{item.date}</span>
              </div>
              <h3>{item.subject}</h3>
              <p className="meta">From: {item.from}</p>
              <p className="summary">
                {clampText(item.what_it_is || item.summary || item.snippet, 140)}
              </p>
              <div className="card-tags">
                <span className="tag">{item.topic || "General"}</span>
                {(item.attachments || []).length > 0 && (
                  <span className="tag">
                    {(item.attachments || []).length} attachments
                  </span>
                )}
              </div>
            </button>
          ))}
        </section>

        {selected && (
          <section className="panel detail">
            <div className="panel-title">Details</div>
            <div className="detail-body">
              <div className="detail-head">
                <h2>{selected.subject}</h2>
                <div className="meta">From: {selected.from}</div>
                <div className="meta">To: {selected.to}</div>
                <div className="meta">Date: {selected.date}</div>
                <div className="detail-actions">
                  <button
                    className="btn ghost icon-btn"
                    type="button"
                    onClick={() => setShowInsight(true)}
                  >
                    <IconSpark /> AI insights
                  </button>
                  <button
                    className="btn ghost"
                    type="button"
                    onClick={() => setSelected(null)}
                  >
                    Close
                  </button>
                  {selected.gmail_url && (
                    <a
                      className="btn ghost icon-btn"
                      href={selected.gmail_url}
                      target="_blank"
                        rel="noopener noreferrer"
                    >
                      <IconExternal /> Open in Gmail
                    </a>
                  )}
                </div>
              </div>

              <div className="detail-section">
                <h4>AI summary</h4>
                {summaryLoading ? (
                  <div className="insight-block">
                    <div className="live-indicator">
                      <span className="live-dot" /> Generating summary
                    </div>
                    <div className="insight-skeleton">
                      <div className="skeleton-line w-60" />
                      <div className="skeleton-line w-90" />
                      <div className="skeleton-line w-75" />
                      <div className="skeleton-line w-80" />
                    </div>
                  </div>
                ) : (
                  <div className="insight-block">
                    <p className="insight-label">What it is</p>
                    <p className="text-block">
                      {renderTextWithLinks(
                        selected.what_it_is ||
                          selected.summary ||
                          selected.snippet ||
                          "No summary available."
                      )}
                    </p>
                    <p className="insight-label">Main offer</p>
                    <p className="text-block">
                      {renderTextWithLinks(
                        selected.main_offer || "Not specified."
                      )}
                    </p>
                    <p className="insight-label">Key benefits</p>
                    {renderBullets(
                      (selected.key_benefits || []).length > 0
                        ? selected.key_benefits
                        : selected.what_it_contains,
                      "No benefits extracted."
                    )}
                    <p className="insight-label">How to open</p>
                    <p className="text-block">
                      {renderTextWithLinks(
                        selected.how_to_open || "Not applicable."
                      )}
                    </p>
                    <p className="insight-label">Important notes</p>
                    {renderBullets(
                      selected.important_notes,
                      "No extra notes detected."
                    )}
                    <p className="insight-label">What you should do</p>
                    {renderBullets(
                      selected.what_you_should_do,
                      "No action suggested."
                    )}
                  </div>
                )}
                <div className="summary-meta">
                  <span className="pill">Topic: {selected.topic || "General"}</span>
                  <span className="pill">Concern: {selected.concern}</span>
                  <span className="pill">
                    {summaryLoading
                      ? "AI: generating..."
                      : `AI: ${selected.provider || "unknown"}`}
                  </span>
                </div>
                <p className="meta">Why received: {selected.why_received}</p>
              </div>

              <div className="detail-section">
                <h4>Sender details</h4>
                <p>From name: {selected.from_name || "Unknown"}</p>
                <p>From email: {selected.from_email || "Unknown"}</p>
                <p>
                  To: {(selected.to_emails || []).join(", ") || selected.to}
                </p>
              </div>

              <div className="detail-section">
                <h4>Why you received this</h4>
                <p>{selected.why_received}</p>
              </div>

              <div className="detail-section">
                <h4>Action items</h4>
                <ul>
                  {(selected.action_items || []).map((item, idx) => (
                    <li key={`${selected.id}-${idx}`}>{item}</li>
                  ))}
                </ul>
              </div>

              <div className="detail-section">
                <h4>Unsubscribe</h4>
                <p>{selected.unsubscribe_instructions}</p>
                {(selected.list_unsubscribe || []).length > 0 ? (
                  <ul>
                    {selected.list_unsubscribe.map((item) => {
                      const isLink =
                        item.startsWith("http") || item.startsWith("mailto:");
                      return (
                        <li key={item}>
                          {isLink ? (
                            <a href={item} target="_blank" rel="noopener noreferrer">
                              {item}
                            </a>
                          ) : (
                            item
                          )}
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <p>No unsubscribe information found.</p>
                )}
              </div>

              {(selected.attachments || []).length > 0 && (
                <div className="detail-section">
                  <div className="detail-section-header">
                    <h4>Attachments</h4>
                    <span className="meta">
                      {(selected.attachments || []).length} files
                    </span>
                  </div>
                  <div className="attachments-list">
                    {(selected.attachments || []).map((attachment, idx) => {
                      const attachmentKey =
                        attachment.attachment_id || attachment.part_id || `${idx}`;
                      const downloadUrl = buildAttachmentUrl(
                        selected.id,
                        attachment,
                        user
                      );
                      const mimeType = String(attachment.mime_type || "");
                      const isPdf =
                        mimeType.toLowerCase() === "application/pdf";
                      const isInline = Boolean(attachment.is_inline);
                      return (
                        <div
                          key={`${selected.id}-att-${attachmentKey}`}
                          className="attachment-block"
                        >
                          <div className="attachment-item">
                            <div className="attachment-meta">
                              <div className="attachment-name">
                                {attachment.filename || "Attachment"}
                              </div>
                              <div className="meta">
                                {mimeType || "application/octet-stream"} -
                                {" "}
                                {formatBytes(attachment.size)}
                                {isInline ? " - inline" : ""}
                              </div>
                            </div>
                            <div className="attachment-actions">
                              {isPdf && downloadUrl && (
                                <button
                                  className="link"
                                  type="button"
                                  onClick={() =>
                                    setAttachmentPreviewId((prev) =>
                                      prev === attachmentKey ? "" : attachmentKey
                                    )
                                  }
                                >
                                  {attachmentPreviewId === attachmentKey
                                    ? "Hide preview"
                                    : "Preview"}
                                </button>
                              )}
                              {downloadUrl && (
                                <>
                                  <a
                                    className="link"
                                    href={downloadUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                  >
                                    Open
                                  </a>
                                  <a
                                    className="link"
                                    href={downloadUrl}
                                    download
                                  >
                                    Download
                                  </a>
                                </>
                              )}
                            </div>
                          </div>
                          {isPdf &&
                            downloadUrl &&
                            attachmentPreviewId === attachmentKey && (
                              <iframe
                                className="attachment-preview"
                                title={`Preview ${
                                  attachment.filename || "attachment"
                                }`}
                                src={downloadUrl}
                              />
                            )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="detail-section">
                <h4>Snippet</h4>
                <p>{selected.snippet}</p>
              </div>

              <div className="detail-section">
                <div className="detail-section-header">
                  <h4>Message</h4>
                </div>
                {selected.body_html ? (
                  <iframe
                    className="mail-html-frame"
                    title="Email HTML preview"
                    sandbox="allow-popups"
                    referrerPolicy="no-referrer"
                    srcDoc={buildHtmlDocument(
                      replaceCidImages(
                        selected.body_html,
                        selected.attachments || [],
                        selected.id
                      )
                    )}
                  />
                ) : (
                  <>
                    <div className={`mail-body ${showFullBody ? "expanded" : ""}`}>
                      {renderTextWithLinks(
                        selected.body || "No body available."
                      )}
                    </div>
                    <button
                      className="link"
                      type="button"
                      onClick={() => setShowFullBody((prev) => !prev)}
                    >
                      {showFullBody ? "Show less" : "Show more"}
                    </button>
                  </>
                )}
              </div>
            </div>
          </section>
        )}
      </main>

      {showInsight && selected && (
        <div className="modal-backdrop" onClick={() => setShowInsight(false)}>
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <div>
                <p className="eyebrow">
                  {insightLoading ? (
                    <span className="live-indicator">
                      <span className="live-dot" /> Summarizing
                    </span>
                  ) : (
                    "AI Insights"
                  )}
                </p>
                <h3>{selected.subject}</h3>
              </div>
              <button
                className="btn ghost"
                type="button"
                onClick={() => setShowInsight(false)}
              >
                Close
              </button>
            </div>
            {insightLoading ? (
              <div className="insight-skeleton">
                <div className="skeleton-line w-60" />
                <div className="skeleton-line w-90" />
                <div className="skeleton-line w-75" />
                <div className="skeleton-line w-80" />
              </div>
            ) : (
              <div className="modal-grid">
                <div>
                  <p className="modal-label">What it is</p>
                  <p>
                    {selected.what_it_is ||
                      selected.summary ||
                      selected.snippet ||
                      "No summary available."}
                  </p>
                  <p className="modal-label">Main offer</p>
                  <p>{selected.main_offer || "Not specified."}</p>
                  <p className="modal-label">Key benefits</p>
                  {renderBullets(
                    (selected.key_benefits || []).length > 0
                      ? selected.key_benefits
                      : selected.what_it_contains,
                    "No benefits extracted."
                  )}
                </div>
                <div>
                  <p className="modal-label">How to open</p>
                  <p>{selected.how_to_open || "Not applicable."}</p>
                  <p className="modal-label">What you should do</p>
                  {renderBullets(
                    selected.what_you_should_do,
                    "No action suggested."
                  )}
                </div>
                <div>
                  <p className="modal-label">Important notes</p>
                  {renderBullets(
                    selected.important_notes,
                    "No extra notes detected."
                  )}
                </div>
                <div>
                  <p className="modal-label">Why you received this</p>
                  <p>{selected.why_received}</p>
                  <p className="modal-label">Unsubscribe</p>
                  <p>{selected.unsubscribe_instructions}</p>
                  {(selected.list_unsubscribe || []).length > 0 ? (
                    <ul>
                      {selected.list_unsubscribe.map((item) => {
                        const isLink =
                          item.startsWith("http") || item.startsWith("mailto:");
                        return (
                          <li key={`modal-${item}`}>
                            {isLink ? (
                              <a href={item} target="_blank" rel="noopener noreferrer">
                                {item}
                              </a>
                            ) : (
                              item
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <p>No unsubscribe information found.</p>
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
    </div>
  );
}

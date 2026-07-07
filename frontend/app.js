const { useState, useEffect, useCallback } = React;

// Change this if the backend is not running on localhost:8000.
const API_BASE = window.GSD_API_BASE || "http://localhost:8000";

function apiFetch(path, token, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers["Authorization"] = "Bearer " + token;
  return fetch(API_BASE + path, { ...options, headers }).then(async (res) => {
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(body.detail || res.statusText);
      err.status = res.status;
      throw err;
    }
    return body;
  });
}

function StatusPill({ value }) {
  return <span className={"status " + value}>{value.replace(/_/g, " ")}</span>;
}

function money(n) {
  return "$" + Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ---------------------------------------------------------------- Login ---
function LoginScreen({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("demo1234");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    apiFetch("/auth/login", null, { method: "POST", body: JSON.stringify({ username, password }) })
      .then((data) => onLogin(data))
      .catch((err) => setError(err.message))
      .finally(() => setBusy(false));
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1>GSD Procurement Integrity</h1>
        <p className="sub">City of Los Angeles &middot; General Services Department</p>
        <form onSubmit={submit}>
          <label>Username</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="j.buyer" autoFocus />
          <label>Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          {error && <div className="error-banner" style={{ marginTop: 14 }}>{error}</div>}
          <button className="primary" disabled={busy}>{busy ? "Signing in..." : "Sign in"}</button>
        </form>
        <div className="demo-hint">
          Demo accounts (password <code>demo1234</code>): j.buyer, r.clerk,
          s.superintendent, f.approver, a.auditor. Every action in this
          system is tied to exactly one of these individually authenticated
          users -- there is no shared login.
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------ Dashboard ---
function Dashboard({ token }) {
  const [vendors, setVendors] = useState([]);
  const [risks, setRisks] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch("/vendors", token).then(async (vs) => {
      setVendors(vs);
      const entries = await Promise.all(
        vs.map((v) => apiFetch(`/vendors/${v.id}/risk`, token).then((r) => [v.id, r]))
      );
      setRisks(Object.fromEntries(entries));
      setLoading(false);
    });
  }, [token]);

  function riskClass(score) {
    if (score >= 40) return "risk-high";
    if (score >= 15) return "risk-mid";
    return "risk-low";
  }

  return (
    <div className="card">
      <h2>Vendor Risk Dashboard</h2>
      <p className="muted" style={{ marginTop: -6, fontSize: 12 }}>
        Rule-based, fully transparent anomaly scoring. Every signal below maps
        to a specific control failure identified in real GSD Fraud, Waste &amp;
        Abuse investigations &mdash; see the project's business_statement.md.
      </p>
      {loading ? <p className="muted">Loading...</p> : (
        <table>
          <thead><tr><th>Vendor</th><th>Risk score</th><th>Signals</th></tr></thead>
          <tbody>
            {vendors.map((v) => {
              const r = risks[v.id];
              return (
                <tr key={v.id}>
                  <td>{v.name}</td>
                  <td className={riskClass(r ? r.risk_score : 0)}>{r ? r.risk_score : "-"}/100</td>
                  <td>
                    {r && r.signals.map((s, i) => (
                      <div key={i} style={{ fontSize: 12 }}>{s}</div>
                    ))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ------------------------------------------------------------- PO List ----
function POList({ token, onOpen }) {
  const [pos, setPos] = useState([]);
  const [vendorsById, setVendorsById] = useState({});

  useEffect(() => {
    apiFetch("/vendors", token).then((vs) => setVendorsById(Object.fromEntries(vs.map((v) => [v.id, v.name]))));
    apiFetch("/purchase-orders", token).then(setPos);
  }, [token]);

  return (
    <div className="card">
      <h2>Purchase Orders</h2>
      <table>
        <thead><tr><th>PO #</th><th>Vendor</th><th>Description</th><th>Amount</th><th>Status</th></tr></thead>
        <tbody>
          {pos.map((po) => (
            <tr key={po.id} className="clickable" onClick={() => onOpen(po.id)}>
              <td>{po.po_number}</td>
              <td>{vendorsById[po.vendor_id] || po.vendor_id}</td>
              <td>{po.description}</td>
              <td>{money(po.total_amount)}</td>
              <td><StatusPill value={po.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --------------------------------------------------------------- New PO ---
function NewPO({ token, user, onCreated }) {
  const [vendors, setVendors] = useState([]);
  const [vendorId, setVendorId] = useState("");
  const [description, setDescription] = useState("");
  const [items, setItems] = useState([{ item_description: "", quantity_ordered: 1, unit_price: 0 }]);
  const [error, setError] = useState(null);

  useEffect(() => { apiFetch("/vendors", token).then((vs) => { setVendors(vs); if (vs[0]) setVendorId(vs[0].id); }); }, [token]);

  if (user.role !== "BUYER") {
    return <div className="card"><p className="muted">Only BUYER accounts can create purchase orders.</p></div>;
  }

  function updateItem(i, field, value) {
    const next = [...items];
    next[i] = { ...next[i], [field]: value };
    setItems(next);
  }

  function submit(e) {
    e.preventDefault();
    setError(null);
    apiFetch("/purchase-orders", token, {
      method: "POST",
      body: JSON.stringify({
        vendor_id: vendorId,
        description,
        line_items: items.map((it) => ({
          item_description: it.item_description,
          quantity_ordered: Number(it.quantity_ordered),
          unit_price: Number(it.unit_price),
        })),
      }),
    })
      .then((po) => onCreated(po.id))
      .catch((err) => setError(err.message));
  }

  return (
    <div className="card">
      <h2>New Purchase Order</h2>
      <form onSubmit={submit}>
        <label>Vendor</label><br />
        <select value={vendorId} onChange={(e) => setVendorId(e.target.value)}>
          {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
        </select>
        <br /><br />
        <label>Description</label><br />
        <input style={{ width: "100%" }} value={description} onChange={(e) => setDescription(e.target.value)} required />
        <h3 style={{ marginTop: 16 }}>Line items</h3>
        {items.map((it, i) => (
          <div key={i} className="inline" style={{ display: "flex", gap: 8, marginBottom: 6 }}>
            <input placeholder="Item description" value={it.item_description}
                   onChange={(e) => updateItem(i, "item_description", e.target.value)} required style={{ flex: 2 }} />
            <input type="number" min="1" placeholder="Qty" value={it.quantity_ordered}
                   onChange={(e) => updateItem(i, "quantity_ordered", e.target.value)} style={{ width: 80 }} />
            <input type="number" min="0" step="0.01" placeholder="Unit price" value={it.unit_price}
                   onChange={(e) => updateItem(i, "unit_price", e.target.value)} style={{ width: 110 }} />
          </div>
        ))}
        <button type="button" className="ghost" onClick={() => setItems([...items, { item_description: "", quantity_ordered: 1, unit_price: 0 }])}>
          + Add line item
        </button>
        {error && <div className="error-banner" style={{ marginTop: 12 }}>{error}</div>}
        <div style={{ marginTop: 14 }}><button className="primary">Create purchase order</button></div>
      </form>
    </div>
  );
}

// ------------------------------------------------------------ PO Detail ---
function PODetail({ token, user, poId, onAudit }) {
  const [po, setPo] = useState(null);
  const [payments, setPayments] = useState([]);
  const [error, setError] = useState(null);
  const [receivingForm, setReceivingForm] = useState({});
  const [paymentForm, setPaymentForm] = useState({ amount: "", is_prepayment: false, justification: "" });

  const reload = useCallback(() => {
    apiFetch(`/purchase-orders/${poId}`, token).then(setPo);
    apiFetch(`/payment-requests?po_id=${poId}`, token).then(setPayments);
  }, [token, poId]);

  useEffect(() => { reload(); }, [reload]);

  if (!po) return <div className="card">Loading...</div>;

  function recordReceiving(lineItemId) {
    const form = receivingForm[lineItemId] || {};
    setError(null);
    apiFetch("/receiving", token, {
      method: "POST",
      body: JSON.stringify({
        line_item_id: lineItemId,
        quantity_received: Number(form.quantity_received || 0),
        serial_or_asset_tag: form.tag || "",
        evidence_note: form.note || "",
      }),
    }).then(reload).catch((err) => setError(err.message));
  }

  function requestPayment(e) {
    e.preventDefault();
    setError(null);
    apiFetch("/payment-requests", token, {
      method: "POST",
      body: JSON.stringify({
        po_id: poId,
        amount: Number(paymentForm.amount),
        is_prepayment: paymentForm.is_prepayment,
        justification: paymentForm.justification || null,
      }),
    }).then(() => { setPaymentForm({ amount: "", is_prepayment: false, justification: "" }); reload(); })
      .catch((err) => setError(err.message));
  }

  function decide(prId, decision) {
    setError(null);
    apiFetch(`/payment-requests/${prId}/decide`, token, {
      method: "POST",
      body: JSON.stringify({ decision }),
    }).then(reload).catch((err) => setError(err.message));
  }

  function release(prId) {
    setError(null);
    apiFetch(`/payment-requests/${prId}/release`, token, { method: "POST" }).then(reload).catch((err) => setError(err.message));
  }

  const canReceive = user.role === "RECEIVING_CLERK";
  const canRequestPayment = user.role === "BUYER" || user.role === "SUPERINTENDENT";
  const canDecide = user.role === "SUPERINTENDENT" || user.role === "FINANCE_APPROVER";
  const canRelease = user.role === "FINANCE_APPROVER";

  return (
    <div>
      <div className="card">
        <h2>{po.po_number} <StatusPill value={po.status} /></h2>
        <p>{po.description}</p>
        <p className="muted">Total: {money(po.total_amount)}</p>
        {error && <div className="error-banner">{error}</div>}
        <button className="ghost" onClick={() => onAudit("PurchaseOrder", po.id)}>View audit trail</button>
      </div>

      <div className="card">
        <h3>Line items &amp; receiving</h3>
        <table>
          <thead><tr><th>Item</th><th>Ordered</th><th>Received</th><th>Evidence</th></tr></thead>
          <tbody>
            {po.line_items.map((li) => {
              const receivedQty = li.receiving_records.reduce((sum, r) => sum + r.quantity_received, 0);
              return (
                <tr key={li.id}>
                  <td>{li.item_description}</td>
                  <td>{li.quantity_ordered} @ {money(li.unit_price)}</td>
                  <td>
                    {receivedQty} / {li.quantity_ordered}
                    {li.receiving_records.map((r) => (
                      <div key={r.id} className="evidence-note">
                        tag {r.serial_or_asset_tag}: "{r.evidence_note}" ({new Date(r.received_at).toLocaleDateString()})
                      </div>
                    ))}
                  </td>
                  <td>
                    {canReceive && (
                      <form className="inline" onSubmit={(e) => { e.preventDefault(); recordReceiving(li.id); }}>
                        <input type="number" placeholder="Qty received" style={{ width: 90 }}
                          onChange={(e) => setReceivingForm({ ...receivingForm, [li.id]: { ...receivingForm[li.id], quantity_received: e.target.value } })} />
                        <input placeholder="Serial / asset tag" style={{ width: 130 }}
                          onChange={(e) => setReceivingForm({ ...receivingForm, [li.id]: { ...receivingForm[li.id], tag: e.target.value } })} />
                        <input placeholder="Evidence note" style={{ width: 200 }}
                          onChange={(e) => setReceivingForm({ ...receivingForm, [li.id]: { ...receivingForm[li.id], note: e.target.value } })} />
                        <button className="primary">Record receiving</button>
                      </form>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>Payment requests</h3>
        <table>
          <thead><tr><th>Amount</th><th>Prepayment?</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {payments.map((pr) => (
              <tr key={pr.id}>
                <td>{money(pr.amount)}</td>
                <td>{pr.is_prepayment ? "Yes (justified)" : "No"}</td>
                <td><StatusPill value={pr.status} /></td>
                <td>
                  {canDecide && pr.status === "PENDING" && (
                    <>
                      <button className="ghost" onClick={() => decide(pr.id, "APPROVE")}>Approve</button>{" "}
                      <button className="ghost" onClick={() => decide(pr.id, "REJECT")}>Reject</button>
                    </>
                  )}
                  {canRelease && pr.status === "APPROVED" && (
                    <button className="primary" onClick={() => release(pr.id)}>Release payment</button>
                  )}
                  <button className="ghost" onClick={() => onAudit("PaymentRequest", pr.id)}>Audit</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {canRequestPayment && (
          <form onSubmit={requestPayment} style={{ marginTop: 14 }}>
            <div className="inline">
              <input type="number" step="0.01" placeholder="Amount" required
                value={paymentForm.amount} onChange={(e) => setPaymentForm({ ...paymentForm, amount: e.target.value })} style={{ width: 120 }} />
              <label style={{ fontSize: 13 }}>
                <input type="checkbox" checked={paymentForm.is_prepayment}
                  onChange={(e) => setPaymentForm({ ...paymentForm, is_prepayment: e.target.checked })} /> Prepayment (before receiving)
              </label>
            </div>
            {paymentForm.is_prepayment && (
              <textarea placeholder="Written justification (required, City Charter compliance)" style={{ marginTop: 8 }}
                value={paymentForm.justification} onChange={(e) => setPaymentForm({ ...paymentForm, justification: e.target.value })} />
            )}
            <div style={{ marginTop: 8 }}><button className="primary">Request payment</button></div>
          </form>
        )}
      </div>
    </div>
  );
}

// ----------------------------------------------------------- Audit View ---
function AuditView({ token, filter }) {
  const [entries, setEntries] = useState([]);

  useEffect(() => {
    const qs = filter ? `?entity_type=${filter.type}&entity_id=${filter.id}` : "";
    apiFetch(`/audit${qs}`, token).then(setEntries);
  }, [token, filter]);

  return (
    <div className="card">
      <h2>Audit Trail {filter ? `— ${filter.type} ${filter.id.slice(0, 8)}…` : "(all)"}</h2>
      <p className="muted" style={{ fontSize: 12, marginTop: -6 }}>
        Append-only. Every state-changing action writes exactly one row here,
        attributed to one authenticated user -- this is what makes "who did
        it" answerable, unlike the shared-login incident this project is
        modeled on.
      </p>
      {entries.map((e) => (
        <div key={e.id} className="audit-entry">
          <strong>{e.action}</strong> on {e.entity_type} {e.entity_id.slice(0, 8)}…
          <div className="meta">by user {e.actor_user_id.slice(0, 8)}… at {new Date(e.created_at).toLocaleString()}</div>
          {e.detail && <div className="meta">{e.detail}</div>}
        </div>
      ))}
      {entries.length === 0 && <p className="muted">No audit entries.</p>}
    </div>
  );
}

// -------------------------------------------------------------- Shell -----
function Shell({ token, user, onLogout }) {
  const [tab, setTab] = useState("dashboard");
  const [openPoId, setOpenPoId] = useState(null);
  const [auditFilter, setAuditFilter] = useState(null);

  function openAudit(type, id) {
    setAuditFilter({ type, id });
    setTab("audit");
  }

  return (
    <div>
      <div className="topbar">
        <div>
          <h1>GSD Procurement Integrity Platform</h1>
          <div className="sub">City of Los Angeles &middot; General Services Department</div>
        </div>
        <div className="who">
          <span>{user.full_name}</span>
          <span className="badge">{user.role}</span>
          <button className="ghost" onClick={onLogout}>Sign out</button>
        </div>
      </div>
      <div className="container">
        <div className="nav">
          <button className={tab === "dashboard" ? "active" : ""} onClick={() => setTab("dashboard")}>Dashboard</button>
          <button className={tab === "pos" ? "active" : ""} onClick={() => { setTab("pos"); setOpenPoId(null); }}>Purchase Orders</button>
          <button className={tab === "new" ? "active" : ""} onClick={() => setTab("new")}>New PO</button>
          <button className={tab === "audit" ? "active" : ""} onClick={() => { setAuditFilter(null); setTab("audit"); }}>Audit Trail</button>
        </div>

        {tab === "dashboard" && <Dashboard token={token} />}
        {tab === "pos" && !openPoId && <POList token={token} onOpen={(id) => setOpenPoId(id)} />}
        {tab === "pos" && openPoId && (
          <div>
            <button className="ghost" style={{ marginBottom: 10 }} onClick={() => setOpenPoId(null)}>&larr; Back to list</button>
            <PODetail token={token} user={user} poId={openPoId} onAudit={openAudit} />
          </div>
        )}
        {tab === "new" && <NewPO token={token} user={user} onCreated={(id) => { setOpenPoId(id); setTab("pos"); }} />}
        {tab === "audit" && <AuditView token={token} filter={auditFilter} />}
      </div>
    </div>
  );
}

// --------------------------------------------------------------- App ------
function App() {
  const [session, setSession] = useState(() => {
    const raw = localStorage.getItem("gsd_session");
    return raw ? JSON.parse(raw) : null;
  });

  function handleLogin(data) {
    const s = { token: data.token, user: { id: data.user_id, full_name: data.full_name, role: data.role } };
    localStorage.setItem("gsd_session", JSON.stringify(s));
    setSession(s);
  }

  function handleLogout() {
    localStorage.removeItem("gsd_session");
    setSession(null);
  }

  if (!session) return <LoginScreen onLogin={handleLogin} />;
  return <Shell token={session.token} user={session.user} onLogout={handleLogout} />;
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);

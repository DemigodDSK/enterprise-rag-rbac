"""Gradio UI for the Aurelius Health Policy Assistant. Exposes a `demo` Blocks object."""
import os

import gradio as gr

from .rag_system import EnterpriseRAGSystem
from .rbac import ROLE_PERMISSIONS

DOCUMENTS_PATH = os.environ.get("DOCUMENTS_PATH", "data/sample_policies")

# Resolve DOCUMENTS_PATH against repo root if not absolute
if not os.path.isabs(DOCUMENTS_PATH):
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(os.getcwd(), DOCUMENTS_PATH),
        os.path.join(here, "..", "..", DOCUMENTS_PATH),
        os.path.join(here, "..", "..", "..", DOCUMENTS_PATH),
    ]
    for c in candidates:
        if os.path.isdir(c):
            DOCUMENTS_PATH = os.path.abspath(c)
            break

rag = EnterpriseRAGSystem(documents_path=DOCUMENTS_PATH)
rag.initialize()

session = {"logged_in": False}

QUICK_QUESTIONS = [
    "What is our leave and attendance policy?",
    "What are the password and MFA requirements?",
    "What is the incident response procedure?",
    "How do I onboard a new employee?",
    "What are the data retention requirements?",
    "What is the anti-harassment policy?",
    "What are vendor confidentiality terms?",
    "What is the business continuity plan?",
]


def do_login(username, password):
    ok = rag.login(username, password)
    if ok:
        u = rag.current_user
        p = ROLE_PERMISSIONS[u.role]
        session["logged_in"] = True
        cats = ", ".join(p["categories"])
        max_cl = p["max_classification"].name.title()

        badge_html = f"""
<div style="display:flex;align-items:center;gap:14px;padding:4px 0;">
  <div style="width:44px;height:44px;border-radius:12px;
    background:linear-gradient(135deg,#0d9488,#0891b2);
    display:flex;align-items:center;justify-content:center;
    font-size:20px;color:white;font-weight:700;flex-shrink:0;">
    {u.full_name[0].upper()}
  </div>
  <div style="min-width:0;">
    <div style="font-weight:700;font-size:15px;color:#f1f5f9;
      white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
      {u.full_name}
    </div>
    <div style="font-size:12px;color:#94a3b8;margin-top:1px;">
      {u.role.value.title()} · {u.department}
    </div>
  </div>
</div>
<div style="margin-top:14px;display:flex;flex-wrap:wrap;gap:6px;">
  <span style="background:#134e4a;color:#5eead4;padding:3px 10px;
    border-radius:20px;font-size:11px;font-weight:600;">
    🔑 {max_cl}
  </span>
  <span style="background:#1e3a5f;color:#7dd3fc;padding:3px 10px;
    border-radius:20px;font-size:11px;font-weight:600;">
    📂 {len(p['categories'])} Categories
  </span>
</div>
"""
        return (
            badge_html,
            gr.update(interactive=True, placeholder="Ask about any Aurelius Health policy..."),
            gr.update(interactive=True),
            gr.update(visible=False),
            gr.update(visible=True),
            [],
        )
    else:
        return (
            "",
            gr.update(interactive=False, placeholder="Login first..."),
            gr.update(interactive=False),
            gr.update(visible=True),
            gr.update(visible=False),
            [],
        )


def do_logout():
    rag.logout()
    session["logged_in"] = False
    return (
        "",
        gr.update(interactive=False, placeholder="Login first..."),
        gr.update(interactive=False),
        gr.update(visible=True),
        gr.update(visible=False),
        [],
    )


def chat_respond(message, history):
    if not message or not message.strip():
        return history, ""
    if not session.get("logged_in") or not rag.current_user:
        history = history or []
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": "🔒 Please sign in first."})
        return history, ""

    history = history or []
    history.append({"role": "user", "content": message})

    r = rag.query(message.strip(), k=3)
    answer = r.get("answer", "No response generated.")

    if r.get("documents"):
        names = []
        for d in r["documents"]:
            n = d.metadata.get("source", "").replace(".md", "").replace("_", " ")
            if n and n not in names:
                names.append(n)
        if names:
            answer += "\n\n---\n**Sources:** " + " · ".join(f"*{n}*" for n in names)

    history.append({"role": "assistant", "content": answer})
    return history, ""


def quick_question(q, history):
    return chat_respond(q, history)


def load_audit():
    if not rag.current_user:
        return "<p style='color:#94a3b8;text-align:center;padding:40px;'>🔒 Sign in with an authorized role to view audit logs.</p>"
    log = rag.get_audit_log(25)
    if isinstance(log, list) and log and "error" in log[0]:
        return f"<p style='color:#f87171;text-align:center;padding:40px;'>🔒 {log[0]['error']}</p>"

    rows = ""
    for e in log:
        t = e["timestamp"].split("T")[1][:8]
        ok = "✅" if e["success"] else "❌"
        q = (e.get("query", "") or "—")[:35]
        action_color = {
            "LOGIN": "#34d399", "QUERY": "#60a5fa",
            "ACCESS_DENIED": "#f87171", "LOGIN_FAILED": "#fb923c",
        }.get(e["action"], "#94a3b8")

        rows += f"""<tr>
          <td style="color:#cbd5e1;font-family:monospace;font-size:12px;">{t}</td>
          <td style="color:#e2e8f0;font-weight:600;">{e['user']}</td>
          <td><span style="color:{action_color};font-weight:600;font-size:12px;">
            {e['action']}</span></td>
          <td style="color:#94a3b8;font-size:13px;">{q}</td>
          <td style="text-align:center;">{e['results']}</td>
          <td style="text-align:center;">{e['rbac_filtered']}</td>
          <td style="text-align:center;">{ok}</td>
        </tr>"""

    return f"""
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr style="border-bottom:2px solid #334155;">
          <th style="text-align:left;padding:10px 8px;color:#64748b;font-size:11px;
            text-transform:uppercase;letter-spacing:1px;">Time</th>
          <th style="text-align:left;padding:10px 8px;color:#64748b;font-size:11px;
            text-transform:uppercase;letter-spacing:1px;">User</th>
          <th style="text-align:left;padding:10px 8px;color:#64748b;font-size:11px;
            text-transform:uppercase;letter-spacing:1px;">Action</th>
          <th style="text-align:left;padding:10px 8px;color:#64748b;font-size:11px;
            text-transform:uppercase;letter-spacing:1px;">Query</th>
          <th style="text-align:center;padding:10px 8px;color:#64748b;font-size:11px;
            text-transform:uppercase;letter-spacing:1px;">Res</th>
          <th style="text-align:center;padding:10px 8px;color:#64748b;font-size:11px;
            text-transform:uppercase;letter-spacing:1px;">Blk</th>
          <th style="text-align:center;padding:10px 8px;color:#64748b;font-size:11px;
            text-transform:uppercase;letter-spacing:1px;">OK</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>"""


def load_stats():
    s = rag.get_stats()
    cards = ""
    icons = {
        "documents": "📄", "parent_chunks": "📦", "child_chunks_indexed": "🔍",
        "retriever": "⚡", "parent_size": "📐", "child_size": "📏",
        "embedding": "🧬", "categories": "📂", "llm": "🤖",
        "llm_enabled": "✅", "audit_entries": "📋",
    }
    for k, v in s.items():
        icon = icons.get(k, "📊")
        label = k.replace("_", " ").title()
        if isinstance(v, bool):
            v = "Active" if v else "Inactive"
        cards += f"""
        <div style="background:#1e293b;border:1px solid #334155;border-radius:12px;
          padding:16px 18px;display:flex;align-items:center;gap:12px;">
          <div style="font-size:22px;width:36px;text-align:center;">{icon}</div>
          <div>
            <div style="font-size:11px;color:#64748b;text-transform:uppercase;
              letter-spacing:0.8px;font-weight:600;">{label}</div>
            <div style="font-size:15px;color:#e2e8f0;font-weight:700;margin-top:2px;">{v}</div>
          </div>
        </div>"""

    return f"""<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));
      gap:12px;">{cards}</div>"""


css = """
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=Playfair+Display:wght@600;700&display=swap');

:root {
    --bg-deep: #0b1120;
    --bg-panel: #111827;
    --bg-card: #1e293b;
    --border: #1e293b;
    --border-hover: #334155;
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --accent: #0d9488;
    --accent-light: #14b8a6;
    --accent-glow: rgba(20,184,166,0.15);
    --cyan: #06b6d4;
}

body, .gradio-container { background: var(--bg-deep) !important; }
.gradio-container {
    max-width: 1280px !important;
    margin: 0 auto !important;
    font-family: 'DM Sans', sans-serif !important;
}

.app-header {
    background: linear-gradient(160deg, #0b1120 0%, #0f1d32 40%, #0c2d2d 100%);
    border: 1px solid #1e293b;
    border-radius: 20px;
    padding: 36px 44px 32px;
    margin-bottom: 20px;
    position: relative;
    overflow: hidden;
}
.app-header .logo {
    font-family: 'Playfair Display', serif;
    font-size: 30px; font-weight: 700;
    color: #f1f5f9;
    letter-spacing: -0.5px;
    display: flex; align-items: center; gap: 14px;
}
.app-header .logo .icon {
    background: linear-gradient(135deg, #0d9488, #06b6d4);
    width: 46px; height: 46px; border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 24px; flex-shrink: 0;
    box-shadow: 0 4px 20px rgba(13,148,136,0.25);
}
.app-header .subtitle {
    color: #64748b; font-size: 14px; margin-top: 6px;
    font-weight: 400; letter-spacing: 0.3px;
}
.app-header .badges {
    display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap;
}
.app-header .badge {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 20px; padding: 4px 14px;
    font-size: 12px; color: #94a3b8; font-weight: 500;
}

.login-card {
    background: linear-gradient(180deg, #111827 0%, #0f172a 100%);
    border: 1px solid #1e293b;
    border-radius: 16px; padding: 28px;
}
.login-card .title {
    font-family: 'Playfair Display', serif;
    font-size: 20px; font-weight: 700;
    color: #f1f5f9; margin-bottom: 20px;
}
.login-card input {
    background: #0b1120 !important;
    border: 1.5px solid #1e293b !important;
    border-radius: 12px !important;
    color: #e2e8f0 !important;
    padding: 11px 16px !important;
    font-size: 14px !important;
}
.login-card input:focus {
    border-color: #0d9488 !important;
    box-shadow: 0 0 0 3px rgba(13,148,136,0.15) !important;
}
.profile-card {
    background: linear-gradient(180deg, #111827 0%, #0f172a 100%);
    border: 1px solid #1e293b;
    border-radius: 16px; padding: 20px;
}

.btn-login {
    background: linear-gradient(135deg, #0d9488 0%, #0891b2 100%) !important;
    border: none !important; color: white !important;
    border-radius: 12px !important; font-weight: 700 !important;
    font-size: 14px !important; padding: 12px 28px !important;
    box-shadow: 0 4px 15px rgba(13,148,136,0.2) !important;
}
.btn-logout {
    background: transparent !important;
    border: 1.5px solid #334155 !important;
    color: #94a3b8 !important;
    border-radius: 10px !important; font-weight: 600 !important;
}
.btn-refresh {
    background: var(--bg-card) !important;
    border: 1px solid #334155 !important;
    color: #94a3b8 !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
}
.qchip {
    background: rgba(13,148,136,0.06) !important;
    border: 1px solid rgba(13,148,136,0.2) !important;
    color: #5eead4 !important;
    border-radius: 10px !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    padding: 7px 14px !important;
    text-align: left !important;
    line-height: 1.35 !important;
}
.qchip:hover {
    background: rgba(13,148,136,0.14) !important;
    border-color: rgba(13,148,136,0.4) !important;
}
.chatbox {
    border: 1px solid #1e293b !important;
    border-radius: 16px !important;
    background: #0b1120 !important;
}
.chat-input input, .chat-input textarea {
    background: #111827 !important;
    border: 1.5px solid #1e293b !important;
    border-radius: 14px !important;
    color: #e2e8f0 !important;
    padding: 13px 18px !important;
    font-size: 14px !important;
}
.btn-send {
    background: linear-gradient(135deg, #0d9488, #0891b2) !important;
    border: none !important; color: white !important;
    border-radius: 14px !important; font-weight: 700 !important;
    font-size: 14px !important;
    min-height: 48px !important;
    box-shadow: 0 4px 15px rgba(13,148,136,0.2) !important;
}
.creds-toggle {
    color: #475569; font-size: 12px; cursor: pointer;
    margin-top: 12px; user-select: none;
}
.creds-toggle summary { list-style: none; }
.creds-toggle summary::-webkit-details-marker { display: none; }
.creds-table table { width: 100%; font-size: 12px; border-collapse: collapse; }
.creds-table th {
    text-align: left; color: #475569; font-weight: 600;
    padding: 4px 8px; border-bottom: 1px solid #1e293b;
    text-transform: uppercase; font-size: 10px; letter-spacing: 0.8px;
}
.creds-table td {
    padding: 5px 8px; color: #94a3b8;
    border-bottom: 1px solid rgba(30,41,59,0.5);
}
.creds-table td:nth-child(1) { color: #e2e8f0; font-weight: 600; }
.section-label {
    font-size: 11px; text-transform: uppercase;
    letter-spacing: 1.2px; color: #475569;
    font-weight: 700; margin: 20px 0 10px;
}
label { color: #94a3b8 !important; font-weight: 500 !important; font-size: 13px !important; }
footer { display: none !important; }
"""


with gr.Blocks(css=css, title="Aurelius Health · Policy Assistant",
               theme=gr.themes.Base()) as demo:

    gr.HTML("""
    <div class="app-header">
        <div class="logo">
            <div class="icon">🏥</div>
            Aurelius Health Systems
        </div>
        <div class="subtitle">Enterprise Policy Assistant</div>
        <div class="badges">
            <span class="badge">RBAC Protected</span>
            <span class="badge">Parent-Child Retrieval</span>
            <span class="badge">LLM-Powered</span>
            <span class="badge">Audit Logged</span>
        </div>
    </div>
    """)

    with gr.Row(equal_height=False):

        with gr.Column(scale=1, min_width=300):

            with gr.Group(visible=True) as login_group:
                gr.HTML('<div class="login-card"><div class="title">🔐 Sign In</div></div>')
                username_in = gr.Textbox(label="Username", placeholder="Enter username",
                                         elem_classes="login-card", max_lines=1, container=True)
                password_in = gr.Textbox(label="Password", type="password",
                                         placeholder="Enter password",
                                         elem_classes="login-card", max_lines=1, container=True)
                login_btn = gr.Button("Sign In →", elem_classes="btn-login", size="lg")

                gr.HTML("""
                <details class="creds-toggle">
                    <summary>▸ View test accounts</summary>
                    <div class="creds-table">
                        <table>
                            <tr><th>User</th><th>Pass</th><th>Role</th></tr>
                            <tr><td>admin</td><td>admin123</td><td>Admin</td></tr>
                            <tr><td>ceo</td><td>exec123</td><td>Executive</td></tr>
                            <tr><td>ciso</td><td>secure123</td><td>Security</td></tr>
                            <tr><td>cco</td><td>comply123</td><td>Compliance</td></tr>
                            <tr><td>hr_manager</td><td>manager123</td><td>Manager</td></tr>
                            <tr><td>john</td><td>employee123</td><td>Employee</td></tr>
                            <tr><td>contractor1</td><td>contract123</td><td>Contractor</td></tr>
                        </table>
                    </div>
                </details>
                """)

            with gr.Group(visible=False) as profile_group:
                profile_html = gr.HTML("", elem_classes="profile-card")
                logout_btn = gr.Button("Sign Out", elem_classes="btn-logout", size="sm")

            gr.HTML('<div class="section-label">💡 Quick Questions</div>')
            qbtns = []
            for q_text in QUICK_QUESTIONS:
                b = gr.Button(q_text, elem_classes="qchip", size="sm", interactive=True)
                qbtns.append((b, q_text))

        with gr.Column(scale=3):
            with gr.Tabs() as tabs:
                with gr.TabItem("💬  Policy Chat", id="chat"):
                    chatbot = gr.Chatbot(
                        height=500, type="messages", show_label=False,
                        elem_classes="chatbox",
                        placeholder="🏥 Sign in to ask about any Aurelius Health policy",
                    )
                    with gr.Row():
                        msg_in = gr.Textbox(
                            show_label=False, placeholder="Login first...",
                            scale=5, max_lines=2, interactive=False,
                            elem_classes="chat-input", container=False,
                        )
                        send_btn = gr.Button(
                            "Send ➤", elem_classes="btn-send",
                            scale=1, interactive=False, min_width=100,
                        )

                with gr.TabItem("📋  Audit Log", id="audit"):
                    audit_btn = gr.Button("🔄 Refresh", elem_classes="btn-refresh", size="sm")
                    audit_out = gr.HTML(
                        "<p style='color:#64748b;text-align:center;padding:40px;'>"
                        "Sign in and click Refresh to load audit data.</p>"
                    )

                with gr.TabItem("📊  System", id="system"):
                    stats_btn = gr.Button("🔄 Refresh", elem_classes="btn-refresh", size="sm")
                    stats_out = gr.HTML(
                        "<p style='color:#64748b;text-align:center;padding:40px;'>"
                        "Click Refresh to load system statistics.</p>"
                    )

    login_outputs = [profile_html, msg_in, send_btn, login_group, profile_group, chatbot]

    login_btn.click(do_login, [username_in, password_in], login_outputs)
    password_in.submit(do_login, [username_in, password_in], login_outputs)
    logout_btn.click(do_logout, [], login_outputs)

    send_btn.click(chat_respond, [msg_in, chatbot], [chatbot, msg_in])
    msg_in.submit(chat_respond, [msg_in, chatbot], [chatbot, msg_in])

    for btn, q_text in qbtns:
        btn.click(quick_question, [gr.State(q_text), chatbot], [chatbot, msg_in])

    audit_btn.click(load_audit, [], audit_out)
    stats_btn.click(load_stats, [], stats_out)

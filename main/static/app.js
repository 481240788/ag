const chatBox = document.getElementById("chatBox");
const conversationInner = document.getElementById("conversationInner");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const newChatButton = document.getElementById("newChatButton");
let activeTaskId = null;
let activeEventSource = null;

const newSessionId = () => crypto.randomUUID();
let sessionId = localStorage.getItem("chat_session_id");
if (!sessionId) {
    sessionId = newSessionId();
    localStorage.setItem("chat_session_id", sessionId);
}

function removeWelcome() {
    const welcome = document.getElementById("welcome");
    if (welcome) welcome.remove();
}

function scrollToLatest() {
    chatBox.scrollTop = chatBox.scrollHeight;
}

function addMessage(content, role, isError = false) {
    removeWelcome();
    const message = document.createElement("div");
    message.className = `message ${role}${isError ? " error" : ""}`;

    if (role === "model") {
        const avatar = document.createElement("div");
        avatar.className = "avatar";
        avatar.textContent = "d";
        avatar.setAttribute("aria-hidden", "true");
        message.appendChild(avatar);
    }

    const contentNode = document.createElement("div");
    contentNode.className = "message-content";
    contentNode.textContent = content;
    message.appendChild(contentNode);
    conversationInner.appendChild(message);
    scrollToLatest();
    return message;
}

function addLoading() {
    const message = addMessage("", "model");
    message.classList.add("loading");
    message.querySelector(".message-content").innerHTML =
        '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
    return message;
}

function resizeInput() {
    messageInput.style.height = "auto";
    messageInput.style.height = `${Math.min(messageInput.scrollHeight, 160)}px`;
}

async function sendMessage() {
    if (activeTaskId) {
        await fetch(`/tasks/${activeTaskId}`, { method: "DELETE" });
        return;
    }
    const message = messageInput.value.trim();
    if (!message) return;

    addMessage(message, "user");
    messageInput.value = "";
    resizeInput();
    sendButton.textContent = "■";
    sendButton.setAttribute("aria-label", "停止任务");
    const loading = addLoading();

    try {
        const response = await fetch("/tasks", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId, message })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.message || "任务创建失败");
        activeTaskId = data.task_id;
        activeEventSource = new EventSource(`/tasks/${activeTaskId}/events`);
        activeEventSource.onmessage = event => {
            const payload = JSON.parse(event.data);
            if (payload.type === "status") {
                loading.querySelector(".message-content").textContent =
                    payload.status === "tool_call"
                        ? `正在使用 ${payload.tool}…`
                        : "正在思考…";
            }
            if (payload.type === "result") {
                loading.remove();
                addMessage(
                    payload.data.answer || "暂时没有得到有效回复，请稍后再试。",
                    "model",
                    payload.status !== "completed"
                );
                finishTask();
            }
            if (payload.type === "cancelled") {
                loading.remove();
                addMessage("任务已取消。", "model", true);
                finishTask();
            }
        };
        activeEventSource.onerror = () => {
            if (activeTaskId) {
                loading.remove();
                addMessage("任务连接已中断，请稍后再试。", "model", true);
                finishTask();
            }
        };
    } catch (error) {
        loading.remove();
        addMessage(`连接失败：${error.message}`, "model", true);
        finishTask();
    }
}

function finishTask() {
    if (activeEventSource) activeEventSource.close();
    activeEventSource = null;
    activeTaskId = null;
    sendButton.textContent = "↑";
    sendButton.setAttribute("aria-label", "发送消息");
    messageInput.focus();
}

async function startNewChat() {
    if (activeTaskId) await fetch(`/tasks/${activeTaskId}`, { method: "DELETE" });
    finishTask();
    const previousSessionId = sessionId;
    sessionId = newSessionId();
    localStorage.setItem("chat_session_id", sessionId);
    conversationInner.innerHTML = `
        <div id="welcome" class="welcome">
            <div class="welcome-mark" aria-hidden="true">d</div>
            <h1>有什么可以帮你？</h1>
            <p>输入一个问题，或从你正在处理的事情开始。</p>
        </div>`;
    try {
        await fetch(`/sessions/${previousSessionId}`, { method: "DELETE" });
    } catch (_) {
        // 服务端清理失败不阻止新建本地会话。
    }
    messageInput.focus();
}

sendButton.addEventListener("click", sendMessage);
newChatButton.addEventListener("click", startNewChat);
messageInput.addEventListener("input", resizeInput);
messageInput.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
});

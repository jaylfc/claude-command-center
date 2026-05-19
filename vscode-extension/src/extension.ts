// Claude Command Center — VS Code extension entry point.
//
// v0.1.0 keeps the surface small on purpose: two palette commands that
// talk to a locally running CCC server (the same one launched by the
// repo's `./run.sh`). A standalone webview replacement for the
// dashboard is explicitly out of scope (see issue #52).

import * as http from 'http';
import * as vscode from 'vscode';

interface SpawnResponse {
    ok?: boolean;
    error?: string;
    code?: string;
    session_id?: string;
    pid?: number;
    name?: string;
}

function getServerConfig(): { host: string; port: number; baseUrl: string } {
    const cfg = vscode.workspace.getConfiguration('claudeCommandCenter');
    const host = cfg.get<string>('host', '127.0.0.1');
    const port = cfg.get<number>('port', 8090);
    return { host, port, baseUrl: `http://${host}:${port}` };
}

function postJson(
    host: string,
    port: number,
    path: string,
    body: object,
    timeoutMs = 5000,
): Promise<{ status: number; data: SpawnResponse }> {
    return new Promise((resolve, reject) => {
        const payload = Buffer.from(JSON.stringify(body), 'utf8');
        const req = http.request(
            {
                host,
                port,
                path,
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': payload.length,
                    // Intentionally omit Origin — CCC's same-origin guard
                    // (`_check_same_origin` in server.py) allows requests
                    // with no Origin header, treating them like curl /
                    // programmatic clients on loopback.
                },
                timeout: timeoutMs,
            },
            (res) => {
                const chunks: Buffer[] = [];
                res.on('data', (c: Buffer) => chunks.push(c));
                res.on('end', () => {
                    const raw = Buffer.concat(chunks).toString('utf8');
                    let data: SpawnResponse = {};
                    try {
                        data = raw ? JSON.parse(raw) : {};
                    } catch {
                        data = { error: `non-JSON response: ${raw.slice(0, 200)}` };
                    }
                    resolve({ status: res.statusCode ?? 0, data });
                });
            },
        );
        req.on('timeout', () => {
            req.destroy(new Error(`timed out after ${timeoutMs}ms`));
        });
        req.on('error', reject);
        req.write(payload);
        req.end();
    });
}

function pickWorkspaceCwd(): string | undefined {
    // Prefer the workspace folder containing the active editor; fall
    // back to the first folder if there's no active editor (e.g.
    // command invoked from the palette with no file open).
    const active = vscode.window.activeTextEditor?.document.uri;
    if (active) {
        const wf = vscode.workspace.getWorkspaceFolder(active);
        if (wf) {
            return wf.uri.fsPath;
        }
    }
    const folders = vscode.workspace.workspaceFolders;
    if (folders && folders.length > 0) {
        return folders[0].uri.fsPath;
    }
    return undefined;
}

async function spawnSession(): Promise<void> {
    const cwd = pickWorkspaceCwd();
    if (!cwd) {
        vscode.window.showWarningMessage(
            'CCC: open a folder in VS Code first — Spawn session needs a working directory.',
        );
        return;
    }

    const prompt = await vscode.window.showInputBox({
        title: 'CCC: Spawn session',
        prompt: `Initial prompt for the new Claude session (cwd: ${cwd})`,
        placeHolder: 'e.g. "Audit the test suite and list slow tests"',
        ignoreFocusOut: true,
    });
    if (!prompt) {
        // User cancelled — silent, no toast.
        return;
    }

    const { host, port, baseUrl } = getServerConfig();
    try {
        const { status, data } = await postJson(host, port, '/api/sessions/spawn', {
            prompt,
            cwd,
        });
        if (status >= 200 && status < 300 && data.ok !== false) {
            const sid = data.session_id ?? data.name ?? 'session';
            const action = await vscode.window.showInformationMessage(
                `CCC: spawned ${sid}`,
                'Open dashboard',
            );
            if (action === 'Open dashboard') {
                vscode.env.openExternal(vscode.Uri.parse(baseUrl));
            }
        } else {
            const msg = data.error ?? `HTTP ${status}`;
            vscode.window.showWarningMessage(`CCC: spawn failed — ${msg}`);
        }
    } catch (err) {
        // Non-modal toast — fail gracefully when CCC isn't running.
        const detail = err instanceof Error ? err.message : String(err);
        vscode.window
            .showWarningMessage(
                `CCC isn't reachable at ${baseUrl} (${detail}). Start it with ./run.sh in the CCC repo.`,
                'Open dashboard URL',
            )
            .then((choice) => {
                if (choice === 'Open dashboard URL') {
                    vscode.env.openExternal(vscode.Uri.parse(baseUrl));
                }
            });
    }
}

function openDashboard(): void {
    const { baseUrl } = getServerConfig();
    vscode.env.openExternal(vscode.Uri.parse(baseUrl));
}

export function activate(context: vscode.ExtensionContext): void {
    context.subscriptions.push(
        vscode.commands.registerCommand('claudeCommandCenter.spawnSession', spawnSession),
        vscode.commands.registerCommand('claudeCommandCenter.openDashboard', openDashboard),
    );
}

export function deactivate(): void {
    // Nothing to clean up — the extension holds no long-lived resources.
}

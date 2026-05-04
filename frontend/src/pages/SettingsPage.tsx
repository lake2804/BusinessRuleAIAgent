import { CheckCircle2, Loader2, Save, XCircle } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";

export function SettingsPage() {
  const [providers, setProviders] = useState<string[]>([]);
  const [models, setModels] = useState<Record<string, string[]>>({});
  const [envConfigured, setEnvConfigured] = useState<Record<string, boolean>>({});
  const [provider, setProvider] = useState("groq");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [health, setHealth] = useState<{ ok: boolean; message: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [sessionKeySaved, setSessionKeySaved] = useState(false);

  const providerModels = useMemo(() => models[provider] || [], [models, provider]);

  useEffect(() => {
    api.settings().then((data) => {
      setProviders(data.providers);
      setModels(data.models);
      setEnvConfigured(data.env_configured);
      setProvider(data.config.provider);
      setModel(data.config.model);
    });
  }, []);

  useEffect(() => {
    if (providerModels.length && !providerModels.includes(model)) {
      setModel(providerModels[0]);
    }
  }, [model, providerModels]);

  useEffect(() => {
    setApiKey(api.getSessionApiKey(provider));
    setSessionKeySaved(Boolean(api.getSessionApiKey(provider)));
  }, [provider]);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setHealth(null);
    try {
      const result = await api.saveSettings({ provider, model, apiKey, checkHealth: true });
      setHealth(result.health || null);
      if (apiKey && result.health?.ok) {
        api.saveSessionApiKey(provider, apiKey);
        setSessionKeySaved(true);
      } else if (apiKey && result.health && !result.health.ok) {
        api.clearSessionApiKey(provider);
        setSessionKeySaved(false);
      }
    } catch (error) {
      setHealth({ ok: false, message: error instanceof Error ? error.message : "Settings save failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="p-5 lg:p-8">
      <header>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="mt-1 text-sm text-slate-500">Provider/model preferences are saved. A working API key is kept for this browser session and used by Review.</p>
      </header>
      <form onSubmit={save} className="mt-6 max-w-2xl rounded-lg border border-slate-200 bg-white p-5">
        <label className="block text-sm font-medium">Provider
          <select value={provider} onChange={(event) => setProvider(event.target.value)} className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
            {providers.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label className="mt-4 block text-sm font-medium">Model
          <select value={model} onChange={(event) => setModel(event.target.value)} className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
            {providerModels.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label className="mt-4 block text-sm font-medium">API key for this session
          <input value={apiKey} onChange={(event) => setApiKey(event.target.value)} type="password" placeholder={envConfigured[provider] ? "Environment key is configured" : "Paste a session-only key"} className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
        </label>
        {sessionKeySaved && (
          <div className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">
            Session key is available for Review in this browser tab.
          </div>
        )}
        <button disabled={busy} className="mt-5 inline-flex items-center gap-2 rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Save and check health
        </button>
        {health && (
          <div className={`mt-5 flex items-start gap-2 rounded-md px-4 py-3 text-sm ${health.ok ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-800"}`}>
            {health.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4" /> : <XCircle className="mt-0.5 h-4 w-4" />}
            <span>{health.message}</span>
          </div>
        )}
      </form>
    </section>
  );
}

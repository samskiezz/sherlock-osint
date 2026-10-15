import { useEffect, useState } from "react";
import { api, post } from "./api";
import { KeyRound, Play } from "lucide-react";
export default function CryptoWorkbench({ notify }: any) {
  const [data, setData] = useState<any>({ algorithms: {}, records: [] }),
    [algorithm, setAlgorithm] = useState("aes_gcm"),
    [operation, setOperation] = useState("encrypt"),
    [key, setKey] = useState(""),
    [input, setInput] = useState("Authorised laboratory test message"),
    [encoding, setEncoding] = useState("utf8"),
    [nonce, setNonce] = useState(""),
    [aad, setAad] = useState(""),
    [result, setResult] = useState<any>(null),
    [busy, setBusy] = useState(false);
  const refresh = () => api("/crypto").then(setData);
  useEffect(() => {
    refresh();
  }, []);
  return (
    <section>
      <h3>Modern authenticated encryption · supplied keys only</h3>
      <div className="notice">
        Keys stay in this request and are excluded from persistent history.
        Plaintext results are returned but not saved. Authenticating ciphertext
        does not verify the truth of its contents.
      </div>
      <div className="two-col">
        <label>
          Algorithm
          <select
            className="field"
            value={algorithm}
            onChange={(e) => setAlgorithm(e.target.value)}
          >
            {Object.entries(data.algorithms).map(([k, v]: any) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          Operation
          <select
            className="field"
            value={operation}
            onChange={(e) => {
              setOperation(e.target.value);
              setEncoding(e.target.value === "encrypt" ? "utf8" : "base64");
            }}
          >
            <option value="encrypt">
              Encrypt owned / authorised test input
            </option>
            <option value="decrypt">Decrypt with known authorised key</option>
          </select>
        </label>
      </div>
      <div className="two-col">
        <label>
          Key · hex · not stored
          <input
            type="password"
            className="field"
            value={key}
            autoComplete="off"
            onChange={(e) => setKey(e.target.value)}
          />
        </label>
        <button
          className="button"
          onClick={() => {
            const n = algorithm === "aes_siv" ? 64 : 32;
            const b = crypto.getRandomValues(new Uint8Array(n));
            setKey(
              Array.from(b, (x) => x.toString(16).padStart(2, "0")).join(""),
            );
          }}
        >
          <KeyRound size={14} /> Generate ephemeral test key
        </button>
      </div>
      <div className="two-col">
        <label>
          Input
          <textarea
            className="field code-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
        </label>
        <label>
          Input encoding
          <select
            className="field"
            value={encoding}
            onChange={(e) => setEncoding(e.target.value)}
          >
            <option value="utf8">UTF-8 (encrypt only)</option>
            <option value="base64">Base64 bytes</option>
            <option value="hex">Hex bytes</option>
          </select>
          <span>Nonce hex · generated fresh when encrypting</span>
          <input
            className="field"
            value={nonce}
            onChange={(e) => setNonce(e.target.value)}
          />
        </label>
      </div>
      <label>
        Associated data (AAD)
        <input
          className="field"
          value={aad}
          onChange={(e) => setAad(e.target.value)}
        />
      </label>
      <button
        className="button primary"
        disabled={busy || !key}
        onClick={async () => {
          setBusy(true);
          try {
            setResult(
              await post("/crypto/run", {
                algorithm,
                operation,
                key_hex: key,
                input,
                encoding,
                nonce_hex: nonce,
                aad,
                authorisation:
                  "Owned or investigator-authorised input; known-key laboratory experiment.",
              }),
            );
            refresh();
          } catch (e: any) {
            notify(e.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Play size={14} /> Run authenticated crypto experiment
      </button>
      {result && (
        <div className="experiment-result">
          <span className="status green">{result.authentication}</span>
          <h4>{result.id}</h4>
          <pre className="forensic-json">
            {result.output_text ?? result.output_base64}
          </pre>
          <p>
            Nonce: {result.nonce_hex || "Algorithm-managed / not applicable"}
          </p>
          <p>{result.validation}</p>
          {result.operation === "encrypt" && (
            <button
              className="button"
              onClick={() => {
                setOperation("decrypt");
                setEncoding("base64");
                setInput(result.output_base64);
                setNonce(result.nonce_hex || "");
              }}
            >
              Use ciphertext for round-trip decryption
            </button>
          )}
        </div>
      )}
      <h3>Crypto audit history · secrets excluded</h3>
      {data.records.map((r: any) => (
        <details key={r.id}>
          <summary>
            {r.data.algorithm} · {r.data.operation} · {r.data.status} · {r.id}
          </summary>
          <pre className="forensic-json">{JSON.stringify(r.data, null, 2)}</pre>
        </details>
      ))}
      <p>{data.key_policy}</p>
    </section>
  );
}

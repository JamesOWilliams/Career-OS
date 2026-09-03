import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import client, { formatError } from "@/lib/api";
import { PageHeader, TrackBadge } from "@/components/primitives";
import { UploadCloud, FileText, Loader2, ArrowRight } from "lucide-react";

export default function ResumeUpload() {
  const inputRef = useRef();
  const navigate = useNavigate();
  const [uploading, setUploading] = useState(false);
  const [proposed, setProposed] = useState([]);
  const [uploads, setUploads] = useState([]);
  const [dragging, setDragging] = useState(false);

  const loadUploads = async () => {
    const { data } = await client.get("/resume/uploads");
    setUploads(data);
  };
  useEffect(() => {
    loadUploads();
  }, []);

  const doUpload = async (file) => {
    if (!file) return;
    setUploading(true);
    setProposed([]);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await client.post("/resume/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setProposed(data.proposed_nodes);
      toast.success(`${data.proposed_nodes.length} proposed node(s) extracted`);
      loadUploads();
    } catch (e) {
      toast.error(formatError(e.response?.data?.detail) || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Ingestion Pipeline"
        title="Resume Ingestion"
        subtitle="Upload a PDF, DOCX or TXT resume. AI extracts structured career knowledge as PROPOSED nodes — never canonical until you verify them."
      />
      <div className="p-8 space-y-6">
        <div
          data-testid="resume-upload-dropzone"
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            doUpload(e.dataTransfer.files?.[0]);
          }}
          className={`co-panel border-dashed cursor-pointer p-12 text-center transition-colors ${
            dragging ? "border-cyan-500 bg-cyan-500/5" : "hover:border-[#31425c]"
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.docx,.txt"
            className="hidden"
            data-testid="resume-file-input"
            onChange={(e) => doUpload(e.target.files?.[0])}
          />
          {uploading ? (
            <div className="flex flex-col items-center gap-3 text-cyan-300">
              <Loader2 className="w-8 h-8 animate-spin" />
              <span className="font-mono text-sm">Extracting structured evidence…</span>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3">
              <div className="w-14 h-14 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center">
                <UploadCloud className="w-7 h-7 text-cyan-400" />
              </div>
              <div className="font-display font-semibold text-lg">Drop resume or click to browse</div>
              <div className="text-sm text-slate-500 font-mono">PDF · DOCX · TXT</div>
            </div>
          )}
        </div>

        {proposed.length > 0 && (
          <div className="co-panel p-5 animate-in" data-testid="extraction-review-table">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="font-display font-semibold">Extraction Review · {proposed.length} proposals</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Review and verify these in Career Profile. They remain PROPOSED until you promote them.
                </p>
              </div>
              <button
                data-testid="goto-profile-btn"
                onClick={() => navigate("/profile")}
                className="flex items-center gap-2 text-sm px-4 py-2 rounded-lg bg-cyan-500/15 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-500/25"
              >
                Review & Verify <ArrowRight className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-2">
              {proposed.map((n) => (
                <div key={n.id} className="node-proposed rounded-lg p-3 flex items-start justify-between gap-3">
                  <div>
                    <div className="font-medium text-sm">
                      {n.identity?.role} · {n.identity?.employer || n.identity?.organization}
                    </div>
                    <div className="font-mono text-[10px] text-slate-500">{n.node_id}</div>
                  </div>
                  <TrackBadge track={n.track} />
                </div>
              ))}
            </div>
          </div>
        )}

        <div>
          <h3 className="font-mono text-xs uppercase tracking-widest text-slate-400 mb-3">Upload history</h3>
          {uploads.length === 0 ? (
            <div className="text-slate-600 text-sm">No uploads yet.</div>
          ) : (
            <div className="grid gap-2 md:grid-cols-3">
              {uploads.map((u) => (
                <div key={u.id} className="co-panel p-3 flex items-center gap-3">
                  <FileText className="w-4 h-4 text-slate-500" />
                  <div className="min-w-0">
                    <div className="text-sm truncate">{u.filename}</div>
                    <div className="font-mono text-[10px] text-slate-500 uppercase">{u.format} · {u.status}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

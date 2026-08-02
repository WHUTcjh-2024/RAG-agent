import { useEffect, useRef, useState } from "react";
import { ArrowUp, ImagePlus, X } from "lucide-react";
import type { Message } from "../types";
import { useTranslation } from "../i18n";

type Props = {
  messages: Message[];
  streaming: boolean;
  onSubmit: (message: string, image: File | null, preview: string | null) => void;
  onCancel?: () => void;
};

export function ChatPanel({ messages, streaming, onSubmit, onCancel }: Props) {
  const { t } = useTranslation();
  const prompts = [t("prompt1"), t("prompt2"), t("prompt3")];
  const [value, setValue] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const selectImage = (file?: File) => {
    if (!file) return;
    if (preview) URL.revokeObjectURL(preview);
    setImage(file);
    setPreview(URL.createObjectURL(file));
  };

  const submit = () => {
    if ((!value.trim() && !image) || streaming) return;
    onSubmit(value.trim(), image, preview);
    setValue("");
    setImage(null);
    setPreview(null);
  };

  return (
    <section className="flex min-h-[600px] flex-col border border-ink/10 bg-paper">
      <div className="border-b border-ink/10 px-5 py-4 text-xs leading-5 text-muted">
        {t("chatIntro")}
      </div>
      <div ref={listRef} className="scrollbar-thin flex-1 space-y-5 overflow-y-auto px-5 py-5">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col justify-between py-2">
            <div>
              <p className="max-w-sm font-display text-[32px] leading-[1.12]">
                {t("dressingFor")}
              </p>
              <p className="mt-4 max-w-sm text-sm leading-6 text-muted">
                {t("chatHelp")}
              </p>
            </div>
            <div className="space-y-2">
              {prompts.map((prompt, index) => (
                <button
                  key={prompt}
                  onClick={() => setValue(prompt)}
                  className="group flex w-full items-center justify-between border-t border-ink/10 py-3 text-left text-sm transition-colors hover:text-accent"
                >
                  <span>{prompt}</span>
                  <span className="font-mono text-[10px] text-muted group-hover:text-accent">0{index + 1}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <div key={message.id} className={message.role === "user" ? "ml-8" : "mr-4"}>
              <p className="mb-1 text-[10px] uppercase tracking-[0.18em] text-muted">
                {message.role === "user" ? "You" : "Atelier"}
              </p>
              <div data-testid={message.role === "assistant" ? "assistant-message" : undefined} className={message.role === "user" ? "bg-ink px-4 py-3 text-sm leading-6 text-white" : "border-l-2 border-accent/50 pl-4 text-sm leading-6"}>
                {message.imagePreview && (
                  <img src={message.imagePreview} className="mb-3 h-28 w-24 object-cover" alt={t("uploadAlt")} />
                )}
                {message.content}
                {streaming && message.role === "assistant" && message === messages.at(-1) && (
                  <span className="ml-1 inline-block h-3 w-px animate-pulse bg-accent" />
                )}
              </div>
            </div>
          ))
        )}
      </div>
      <div className="border-t border-ink/10 p-4">
        {preview && (
          <div className="mb-3 flex items-center gap-3 bg-canvas p-2">
            <img src={preview} className="h-14 w-12 object-cover" alt={t("preview")} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium">{image?.name}</p>
              <p className="mt-0.5 text-[10px] text-muted">{t("visualSearch")}</p>
            </div>
            <button onClick={() => { setImage(null); setPreview(null); }} className="p-2 text-muted hover:text-ink">
              <X size={15} />
            </button>
          </div>
        )}
        <div className="flex items-end gap-2 border border-ink/15 bg-white p-2 focus-within:border-ink/40">
          <label className="cursor-pointer p-2 text-muted transition-colors hover:text-ink" aria-label={t("upload")}>
            <ImagePlus size={19} strokeWidth={1.5} />
            <input type="file" accept="image/*" className="hidden" onChange={(event) => selectImage(event.target.files?.[0])} />
          </label>
          <textarea
            data-testid="agent-message"
            aria-label={t("request")}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); submit(); }
            }}
            rows={2}
            placeholder={t("chatPlaceholder")}
            className="max-h-28 min-h-11 flex-1 resize-none bg-transparent px-1 py-2 text-sm outline-none placeholder:text-muted/70"
          />
          <button aria-label={streaming ? "取消请求" : t("send")} onClick={streaming ? onCancel : submit} disabled={!streaming && (!value.trim() && !image)} className="grid h-10 w-10 shrink-0 place-items-center bg-accent text-white transition-colors hover:bg-accent-dark disabled:cursor-not-allowed disabled:bg-ink/15">
            {streaming ? <X size={17} /> : <ArrowUp size={17} />}
          </button>
        </div>
      </div>
    </section>
  );
}

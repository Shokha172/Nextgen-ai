"use client";

import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  Input,
  PageHeader,
  Spinner,
  useToast,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

interface ChatMessage {
  id: string;
  sender: "user" | "ai";
  text: string;
  groundingPassed?: boolean;
  suggestions?: Array<{ text: string }>;
  ts: string;
}

export default function AdvisorPage() {
  const { t, lang } = useI18n();
  const { toast } = useToast();
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      sender: "ai",
      text: "Assalomu alaykum! Men NEXTGEN AI korxona energetika tahlilchisiman. Korxonangiz elektr iste'moli, anomaliyalar, smenalar va xarajatlar bo‘yicha har qanday savolingizga javob bera olaman.",
      groundingPassed: true,
      ts: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);

  const quickQuestions = [
    t("advisor.q1"),
    t("advisor.q2"),
    t("advisor.q3"),
    t("advisor.q4"),
    t("advisor.q5"),
    t("advisor.q6"),
  ];

  const handleAsk = async (queryText?: string) => {
    const q = (queryText ?? question).trim();
    if (!q || loading) return;

    const userMsg: ChatMessage = {
      id: String(Date.now()),
      sender: "user",
      text: q,
      ts: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setQuestion("");
    setLoading(true);

    try {
      const res = await api.post<{
        answer: string;
        grounding?: { passed: boolean };
        suggestions?: Array<{ text: string }>;
      }>("/ai/ask", {
        question: q,
        language: lang in ["uz", "ru", "en"] ? lang : "uz",
      });

      const aiMsg: ChatMessage = {
        id: String(Date.now() + 1),
        sender: "ai",
        text: res.answer,
        groundingPassed: res.grounding?.passed ?? true,
        suggestions: res.suggestions,
        ts: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => [...prev, aiMsg]);
    } catch {
      toast({
        title: "Xatolik",
        body: "AI javobini olishda uzilish bo‘ldi. Qayta urinib ko‘ring.",
        tone: "danger",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={t("advisor.title")}
        subtitle={t("advisor.subtitle")}
        actions={
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-lg border border-primary/20 bg-primary/5 px-2.5 py-1 text-[11px] font-medium text-primary sm:flex">
              👨‍💻 Dev: Shohjahon Abdullayev
            </span>
            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                setMessages([
                  {
                    id: "welcome-reset",
                    sender: "ai",
                    text: "Suhbat yangilandi. Iste'mol, yuklanishlar va anomaliyalar bo‘yicha savol bering.",
                    groundingPassed: true,
                    ts: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                  },
                ])
              }
            >
              {t("advisor.new_chat")}
            </Button>
          </div>
        }
      />

      {/* Suggested Quick Questions */}
      <div className="flex flex-wrap gap-2">
        {quickQuestions.map((q, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => void handleAsk(q)}
            className="rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-muted transition-colors hover:border-primary/50 hover:bg-primary/5 hover:text-primary"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Chat Area */}
      <Card className="flex min-h-[480px] flex-col justify-between p-4 sm:p-6">
        <div className="flex flex-col gap-4 overflow-y-auto">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex flex-col ${msg.sender === "user" ? "items-end" : "items-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 text-[13px] leading-relaxed ${
                  msg.sender === "user"
                    ? "bg-[#155EEF] text-white shadow-xs"
                    : "border border-line bg-surface2/60 text-ink shadow-xs"
                }`}
              >
                <div className="whitespace-pre-wrap">{msg.text}</div>

                {msg.sender === "ai" && (
                  <div className="mt-2.5 flex items-center justify-between border-t border-line/40 pt-1.5 text-[10px] text-muted">
                    <span className="flex items-center gap-1">
                      {msg.groundingPassed ? (
                        <span className="text-success">✓ {t("advisor.guard_passed")}</span>
                      ) : (
                        <span className="text-warning">⚠️ Deterministik xavfsiz javob</span>
                      )}
                    </span>
                    <span>{msg.ts}</span>
                  </div>
                )}
              </div>

              {msg.suggestions && msg.suggestions.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {msg.suggestions.map((s, si) => (
                    <button
                      key={si}
                      type="button"
                      onClick={() => void handleAsk(s.text)}
                      className="text-[11px] text-primary underline underline-offset-2 hover:text-[#124bbf]"
                    >
                      • {s.text}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex items-center gap-2 text-xs text-muted">
              <Spinner className="h-4 w-4" />
              <span>{t("advisor.thinking")}</span>
            </div>
          )}
        </div>

        {/* Input Bar */}
        <div className="mt-6 flex flex-col gap-2 border-t border-line pt-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void handleAsk();
            }}
            className="flex items-center gap-2"
          >
            <Input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder={t("advisor.ask_placeholder")}
              className="flex-1"
              disabled={loading}
            />
            <Button
              type="submit"
              variant="primary"
              className="bg-[#155EEF] hover:bg-[#124bbf]"
              loading={loading}
            >
              {t("advisor.send")}
            </Button>
          </form>
          <p className="text-[11px] text-muted">{t("advisor.disclaimer")}</p>
        </div>
      </Card>
    </div>
  );
}

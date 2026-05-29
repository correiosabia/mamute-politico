import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Header } from '@/components/layout/Header';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Bot, User, PlusCircle, Send } from 'lucide-react';
import {
  streamChat,
  ChatbotStreamError,
  type ChatMessagePayload,
} from '@/api/chatbot';
import logoMamute from '@/assets/logo-mamute.png';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

const exampleQuestions = [
  'Quais foram os projetos de lei sobre educação apresentados em 2024?',
  'Como votou o Deputado João Silva na reforma tributária?',
  'Quantas proposições foram aprovadas este mês?',
  'Quais senadores mais discursaram sobre meio ambiente?',
];

const MIN_QUESTION_LEN = 1;

const PesquisaIAPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content:
        'Olá! Sou o assistente de pesquisa legislativa do Mamute Político. Posso ajudá-lo a encontrar informações sobre parlamentares, proposições, votações e discursos. Como posso ajudar você hoje?',
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [hueRingBurst, setHueRingBurst] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const threadBottomRef = useRef<HTMLDivElement>(null);
  const messageInputRef = useRef<HTMLInputElement>(null);
  const prevMessageCountRef = useRef<number | null>(null);
  const messagesRef = useRef<Message[]>(messages);
  messagesRef.current = messages;
  const urlAutoSendConsumed = useRef(false);

  useLayoutEffect(() => {
    const n = messages.length;
    const prev = prevMessageCountRef.current;
    prevMessageCountRef.current = n;
    if (prev !== null && n > prev) {
      threadBottomRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' });
    }
  }, [messages.length]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const sendQuestion = useCallback(async (questionRaw: string) => {
    const question = questionRaw.trim();
    if (!question) return;
    if (question.length < MIN_QUESTION_LEN) {
      toast.error(`Digite pelo menos ${MIN_QUESTION_LEN} caracteres.`);
      return;
    }

    abortRef.current?.abort();

    const historyForApi: ChatMessagePayload[] = messagesRef.current.map(({ role, content }) => ({
      role,
      content,
    }));

    const userMessage: Message = {
      id: `${Date.now()}-u`,
      role: 'user',
      content: question,
      timestamp: new Date(),
    };
    const assistantId = `${Date.now()}-a`;

    setInput('');
    setMessages((prev) => {
      let next = [...prev];
      const last = next[next.length - 1];
      if (last?.role === 'assistant' && last.content === '') {
        next = next.slice(0, -1);
      }
      return [
        ...next,
        userMessage,
        { id: assistantId, role: 'assistant', content: '', timestamp: new Date() },
      ];
    });

    const controller = new AbortController();
    abortRef.current = controller;

    let pending = '';
    let rafId = 0;

    const flushPending = () => {
      if (!pending) return;
      const chunk = pending;
      pending = '';
      setMessages((prev) =>
        prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + chunk } : m))
      );
    };

    const scheduleFlush = () => {
      if (rafId) return;
      rafId = requestAnimationFrame(() => {
        rafId = 0;
        flushPending();
      });
    };

    try {
      await streamChat({
        question,
        history: historyForApi,
        signal: controller.signal,
        onToken: (t) => {
          pending += t;
          scheduleFlush();
        },
      });
      if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
      flushPending();
    } catch (e) {
      if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
      pending = '';
      if (e instanceof DOMException && e.name === 'AbortError') {
        setMessages((prev) =>
          prev.filter((m) => !(m.id === assistantId && m.role === 'assistant' && !m.content))
        );
        return;
      }
      const msg =
        e instanceof ChatbotStreamError
          ? e.message
          : 'Falha ao contactar o assistente. Tente novamente.';
      toast.error(msg);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId && m.role === 'assistant' && !m.content
            ? { ...m, content: 'Não foi possível obter uma resposta agora.' }
            : m
        )
      );
    }
  }, []);

  useEffect(() => {
    if (searchParams.get('autoSend') !== '1') {
      urlAutoSendConsumed.current = false;
      return;
    }
    const pergunta = searchParams.get('pergunta')?.trim();
    if (!pergunta || pergunta.length < MIN_QUESTION_LEN) return;
    if (urlAutoSendConsumed.current) return;

    urlAutoSendConsumed.current = true;
    setSearchParams({}, { replace: true });
    void sendQuestion(pergunta);
  }, [searchParams, setSearchParams, sendQuestion]);

  const handleSend = () => {
    void sendQuestion(input);
  };

  const canSend = input.trim().length >= MIN_QUESTION_LEN;

  return (
    <div className="min-h-screen" style={{ background: 'linear-gradient(to bottom, #efeeee 0%, #efeeee 70%, #1b76ff 70%, #1b76ff 100%)' }}>
      <Header />

      <main className="container py-8">
        {/* Page title */}
        <div className="mb-8 flex flex-col w-full gap-[28px]">
          <h1 className="text-center md:text-left text-[36px] md:text-[48px] leading-none font-bold text-[#383838]">Pesquisa IA</h1>
          <p className="text-center md:text-left mt-2 max-w-4xl text-[18px] font-normal leading-snug text-[#383838]">
            Consulte dados legislativos em linguagem natural. Acesse um banco de dados com as proposições, votações e discursos.
            Combine SQL + processamento de linguagem natural para uma abordagem híbrida.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[5fr_7fr]">
          {/* Perguntas sugeridas */}
          <div className="mp-card flex flex-col bg-white p-8 lg:h-[564px]">
            <h2 className="mb-5 text-[32px] font-bold leading-none text-[#090909]">Perguntas sugeridas</h2>
            <div className="flex min-h-0 flex-col gap-[18px] overflow-auto flex-1">
              {exampleQuestions.map((question, index) => (
                <button
                  key={index}
                  type="button"
                  onClick={() => {
                    setInput(question);
                    queueMicrotask(() => messageInputRef.current?.focus());
                  }}
                  className="mp-card flex min-h-[98px] w-full items-center border border-black/10 bg-white px-5 text-left transition hover:bg-[#f5f5f5]"
                >
                  <span className="flex w-full items-center justify-between gap-4">
                    <span className="text-[15px] font-semibold text-[#383838] leading-tight">
                      {question}
                    </span>
                    <PlusCircle className="h-9 w-9 shrink-0 text-[#09e03b]" />
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Chat bot */}
          <div className="mp-card flex flex-col bg-white lg:h-[564px]">
            <div className="flex items-center gap-4 border-b px-8 py-6">
              <Bot className="h-12 w-12 shrink-0 text-[#090909]" />
              <h2 className="text-[32px] leading-none font-bold text-[#090909]">Chat Bot</h2>
            </div>

            <ScrollArea className="min-h-[240px] flex-1 px-8 py-4">
              <div className="space-y-4">
                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    {message.role === 'assistant' && (
                      <Avatar className="h-8 w-8 shrink-0">
                        <AvatarFallback className="bg-[#468fff] text-white">
                          <Bot className="h-4 w-4" />
                        </AvatarFallback>
                      </Avatar>
                    )}
                    <div
                      className={`rounded-[28px] p-4 ${
                        message.role === 'user'
                          ? 'max-w-[65%] bg-[#09e03b] text-white'
                          : 'max-w-[92%] bg-[#f5f5f5] text-[#383838]'
                      }`}
                    >
                      {message.role === 'assistant' && message.content === '' ? (
                        <div className="flex gap-1 py-1">
                          {[0, 150, 300].map((delay) => (
                            <span
                              key={delay}
                              className="h-2 w-2 rounded-full bg-[#1b76ff] animate-bounce"
                              style={{ animationDelay: `${delay}ms` }}
                            />
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                      )}
                      <p className={`mt-2 text-xs ${message.role === 'user' ? 'text-white/70' : 'text-[#383838]/50'}`}>
                        {message.timestamp.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </div>
                    {message.role === 'user' && (
                      <Avatar className="h-8 w-8 shrink-0">
                        <AvatarFallback className="bg-[#383838] text-white">
                          <User className="h-4 w-4" />
                        </AvatarFallback>
                      </Avatar>
                    )}
                  </div>
                ))}
                <div ref={threadBottomRef} aria-hidden className="h-0 w-full shrink-0" />
              </div>
            </ScrollArea>

            <div className="border-t px-8 py-4">
              <form
                onSubmit={(e) => { e.preventDefault(); void handleSend(); }}
                className="flex gap-3"
              >
                <div className="relative flex min-w-0 flex-1">
                  <Input
                    ref={messageInputRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onFocus={() => setHueRingBurst((k) => k + 1)}
                    placeholder="Digite sua pergunta sobre dados legislativos..."
                    className="peer relative z-[1] w-full rounded-full border-0 bg-[#efeeee] text-[13px] text-[#7f7b7b] placeholder:text-[#7f7b7b] focus-visible:ring-0"
                    minLength={MIN_QUESTION_LEN}
                  />
                  <div
                    key={hueRingBurst}
                    aria-hidden
                    className="pointer-events-none absolute -inset-[4px] z-0 rounded-full border-2 border-[#1b76ff] opacity-0 peer-focus-visible:opacity-100 motion-safe:animate-pesquisa-input-ring-hue motion-reduce:animate-none"
                  />
                </div>
                <button
                  type="submit"
                  disabled={!canSend}
                  className="flex shrink-0 items-center justify-center gap-2 rounded-full bg-[#1b76ff] px-4 md:px-3 py-2 text-[13px] font-bold uppercase text-white transition hover:opacity-90 disabled:opacity-50 sm:px-6"
                >
                  <span className="sr-only sm:not-sr-only sm:inline">ENVIAR</span>
                  <Send className="h-3.5 w-3.5 shrink-0" aria-hidden />
                </button>
              </form>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="mt-8 py-6">
        <div className="container flex items-center justify-between">
          <img src={logoMamute} alt="Mamute Político" className="h-[47px] w-auto brightness-0 invert" />
          <span className="text-[12px] font-medium text-white">
            2026 Mamute Político. Dados obtidos via API aberta do Congresso Nacional.
          </span>
        </div>
      </footer>
    </div>
  );
};

export default PesquisaIAPage;

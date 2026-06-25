import type { NodeDataShape } from './types';
import { mergeDefaultData } from './defaults';

/**
 * IMDF Migration — from penguin-canvas (T8mars)
 * Source: /mnt/d/Hermes/imdf_vendor/penguin-canvas/src/components/nodes/
 * Renamed: PascalCase -> snake_case
 * This file is a physical copy; no logic has been rewritten.
 */

/**
 * ─── R3-Worker-4 IO CONTRACT MARKER ────────────────────────────────
 * 类型 key : grok-oauth-agent
 * 组件     : GrokOAuthAgentNode
 * Data in  : NodeDataShape<'grok-oauth-agent'> (用户/上游配置 + 节点自身状态)
 * Data out : imageUrl/videoUrl/audioUrl/prompt/outputText 写回 data
 * 默认值   : mergeDefaultData('grok-oauth-agent', p.data) → defaults.ts
 * IO 文档   : NODE_IO_CONTRACTS → 类型 'grok-oauth-agent'
 * onChange : useUpdateNodeData(id).update(patch) 浅合并到 data
 * ────────────────────────────────────────────────────────────────────
 */


import { memo, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import {
  AlertCircle,
  Bot,
  Image as ImageIcon,
  Loader2,
  LogIn,
  LogOut,
  MessageCircle,
  Mic,
  Music2,
  RefreshCw,
  Send,
  Square,
  Video,
  Wand2,
} from 'lucide-react';
import { PORT_COLOR } from '../../config/portTypes';
import { useRunTrigger } from '../../hooks/useRunTrigger';
import {
  generateGrokOAuthImage,
  generateGrokOAuthTts,
  getGrokOAuthStatus,
  GROK_OAUTH_PRIVATE_DISABLED_MESSAGE,
  logoutGrokOAuth,
  pollGrokOAuthLogin,
  queryGrokOAuthVideoStatus,
  startGrokOAuthLogin,
  streamGrokOAuthChat,
  submitGrokOAuthVideo,
  transcribeGrokOAuthAudio,
  type GrokOAuthStatus,
} from '../../services/grokOAuth';
import { logBus } from '../../stores/logs';
import { taskCompletionSound } from '../../stores/taskCompletionSound';
import { useThemeStore } from '../../stores/theme';
import { useOrderedMaterials } from './useOrderedMaterials';
import { useUpdateNodeData } from './useUpdateNodeData';
import { useUpstreamMaterials, type Material } from './useUpstreamMaterials';
import MaterialPreviewSection from './MaterialPreviewSection';
import MentionPromptInput from './MentionPromptInput';
import SmartImage from '../SmartImage';
import { resolveMediaMentions, type MediaMention } from './mediaMentions';

type GrokOAuthMode = 'chat' | 'image' | 'video' | 'tts' | 'stt';

const MODES: Array<{ id: GrokOAuthMode; label: string; icon: any }> = [
  { id: 'chat', label: '流式聊天', icon: MessageCircle },
  { id: 'image', label: '图像', icon: ImageIcon },
  { id: 'video', label: '视频', icon: Video },
  { id: 'tts', label: 'TTS', icon: Music2 },
  { id: 'stt', label: 'STT', icon: Mic },
];

const CHAT_MODELS = ['grok-4.3', 'grok-4', 'grok-4-fast-non-reasoning', 'grok-4.20-reasoning'];
const IMAGE_MODELS = ['grok-imagine-image', 'grok-imagine-image-quality'];
const VIDEO_MODELS = ['grok-imagine-video-1.5-preview', 'grok-imagine-video'];
const RATIOS = ['1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3'];
const RESOLUTIONS = ['720p', '480p', '1k', '2k'];

const handleStyle: CSSProperties = {
  width: 12,
  height: 12,
  border: 'none',
  zIndex: 20,
};

function sleep(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }
    const timer = window.setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      window.clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    }, { once: true });
  });
}

function asStringArray(value: any): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item || '').trim()).filter(Boolean);
  const text = String(value || '').trim();
  return text ? [text] : [];
}

function buildPrompt(localPrompt: string, upstreamTexts: Material[], mentions: MediaMention[], mentionMaterials: Material[]) {
  const upstreamText = upstreamTexts.map((item) => item.url).filter(Boolean).join('\n\n').trim();
  const resolvedLocal = resolveMediaMentions(localPrompt || '', mentions || [], mentionMaterials).trim();
  return [upstreamText, resolvedLocal].filter(Boolean).join('\n\n').trim();
}

const GrokOAuthAgentNode = ({ id, data, selected }: NodeProps) => {
  const update = useUpdateNodeData(id);
  const d = mergeDefaultData('grok-oauth-agent', (data as Partial<NodeDataShape<'grok-oauth-agent'>>) || undefined);
  const { theme, style: themeStyle } = useThemeStore();
  const isDark = theme === 'dark';
  const isLight = theme === 'light';
  const isPixel = themeStyle === 'pixel';

  const [status, setStatus] = useState<GrokOAuthStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [streamingReply, setStreamingReply] = useState('');
  const [loginPolling, setLoginPolling] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const loginPollRef = useRef<number | null>(null);

  const mode = (d.mode || 'chat') as GrokOAuthMode;
  const localPrompt = String(d.prompt || '');
  const promptMentions = (Array.isArray(d.promptMentions) ? d.promptMentions : []) as MediaMention[];
  const materialOrder = Array.isArray(d.materialOrder) ? d.materialOrder : [];
  const statusText = String(d.status || 'idle');
  const isBusy = ['running', 'streaming', 'submitting', 'polling'].includes(statusText);

  const upstream = useUpstreamMaterials(id);
  const orderedTexts = useOrderedMaterials(upstream.texts, materialOrder);
  const orderedImages = useOrderedMaterials(upstream.images, materialOrder);
  const orderedVideos = useOrderedMaterials(upstream.videos, materialOrder);
  const orderedAudios = useOrderedMaterials(upstream.audios, materialOrder);
  const mentionMaterials = useMemo(
    () => [...orderedImages, ...orderedVideos, ...orderedAudios],
    [orderedImages, orderedVideos, orderedAudios],
  );

  const imageUrls = asStringArray(d.imageUrls || d.imageUrl);
  const videoUrls = asStringArray(d.videoUrls || d.videoUrl);
  const audioUrls = asStringArray(d.audioUrls || d.audioUrl);
  const outputText = String(d.outputText || d.reply || d.text || '');
  const error = String(d.error || '');

  const accent = isPixel ? 'var(--px-mint)' : isLight ? '#10b981' : '#67e8f9';
  const bg = isPixel ? 'var(--px-surface)' : isLight ? '#ffffff' : 'rgba(7, 12, 24, 0.96)';
  const surface = isPixel ? 'var(--px-muted)' : isLight ? 'rgba(16,185,129,0.08)' : 'rgba(255,255,255,0.06)';
  const surfaceStrong = isPixel ? 'var(--px-yellow)' : isLight ? 'rgba(16,185,129,0.16)' : 'rgba(103,232,249,0.14)';
  const text = isPixel ? 'var(--px-ink)' : isLight ? '#0f172a' : '#ecfeff';
  const subText = isPixel ? 'var(--px-ink-soft)' : isLight ? '#64748b' : 'rgba(236,254,255,0.62)';
  const border = isPixel ? 'var(--px-ink)' : isLight ? 'rgba(16,185,129,0.28)' : 'rgba(103,232,249,0.24)';
  const danger = isPixel ? '#dc2626' : '#fca5a5';

  const rootStyle: CSSProperties = {
    width: 420,
    minHeight: 520,
    background: bg,
    color: text,
    border: `2px solid ${selected ? accent : border}`,
    borderRadius: isPixel ? 8 : 16,
    boxShadow: isPixel ? (selected ? '5px 5px 0 var(--px-ink)' : '3px 3px 0 var(--px-ink)') : 'var(--t8-node-shadow, 0 16px 42px rgba(0,0,0,0.32))',
    overflow: 'visible',
  };

  const refreshStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const next = await getGrokOAuthStatus();
      setStatus(next);
      update({
        oauthAvailable: !!next.available,
        oauthLoggedIn: !!next.loggedIn,
        oauthMessage: next.message || '',
      });
    } catch (e: any) {
      const message = e?.message || String(e);
      setStatus({ available: false, loggedIn: false, message });
      update({ oauthAvailable: false, oauthLoggedIn: false, oauthMessage: message });
    } finally {
      setStatusLoading(false);
    }
  }, [update]);

  useEffect(() => {
    void refreshStatus();
    return () => {
      abortRef.current?.abort();
      if (loginPollRef.current) window.clearTimeout(loginPollRef.current);
    };
  }, [refreshStatus]);

  const startLoginPoll = useCallback((sessionId: string) => {
    setLoginPolling(true);
    const tick = async () => {
      try {
        const result = await pollGrokOAuthLogin({ sessionId });
        if (result.loggedIn || result.status === 'success' || result.done) {
          setLoginPolling(false);
          await refreshStatus();
          logBus.success('Grok OAuth 登录完成', `grok:${id}`);
          return;
        }
        loginPollRef.current = window.setTimeout(tick, 1800);
      } catch (e: any) {
        setLoginPolling(false);
        update({ error: e?.message || String(e) });
      }
    };
    loginPollRef.current = window.setTimeout(tick, 1200);
  }, [id, refreshStatus, update]);

  const handleLogin = useCallback(async () => {
    try {
      update({ error: '' });
      const result = await startGrokOAuthLogin({});
      const loginUrl = result.loginUrl || result.url || result.verificationUriComplete || result.verification_url;
      if (loginUrl && typeof window !== 'undefined') {
        window.open(loginUrl, '_blank', 'noopener,noreferrer');
      }
      const sessionId = String(result.sessionId || result.deviceCode || result.state || '').trim();
      if (sessionId) {
        startLoginPoll(sessionId);
      } else {
        await refreshStatus();
      }
    } catch (e: any) {
      const message = e?.message || String(e);
      update({ error: message });
      logBus.error(message, `grok:${id}`);
    }
  }, [id, refreshStatus, startLoginPoll, update]);

  const handleLogout = useCallback(async () => {
    try {
      await logoutGrokOAuth();
      await refreshStatus();
      update({ error: '' });
    } catch (e: any) {
      update({ error: e?.message || String(e) });
    }
  }, [refreshStatus, update]);

  const setMaterialOrder = (newOrder: string[]) => update({ materialOrder: newOrder });

  const payloadBase = useCallback(() => {
    const promptResolved = buildPrompt(localPrompt, orderedTexts, promptMentions, mentionMaterials);
    return {
      mode,
      prompt: promptResolved,
      promptResolved,
      text: promptResolved,
      images: orderedImages.map((item) => item.url),
      videos: orderedVideos.map((item) => item.url),
      audios: orderedAudios.map((item) => item.url),
      mentions: promptMentions,
      nodeId: id,
    };
  }, [id, localPrompt, mentionMaterials, mode, orderedAudios, orderedImages, orderedTexts, orderedVideos, promptMentions]);

  const handleVideoSubmit = useCallback(async (controller: AbortController) => {
    const promptPayload = payloadBase();
    const first = await submitGrokOAuthVideo({
      ...promptPayload,
      model: d.videoModel || VIDEO_MODELS[0],
      ratio: d.ratio || '16:9',
      aspectRatio: d.ratio || '16:9',
      resolution: d.videoResolution || '720p',
      duration: Number(d.duration || 8),
    });
    const requestId = first.requestId || first.id || first.taskId || first.generationId;
    if (first.videoUrl || (first.videoUrls && first.videoUrls.length > 0)) return first;
    if (!requestId) return first;

    update({ requestId, progress: first.progress || 0, status: 'polling', progressMessage: first.message || '视频任务已提交，正在轮询...' });
    for (let i = 0; i < 120; i += 1) {
      await sleep(3500, controller.signal);
      const next = await queryGrokOAuthVideoStatus({ requestId, model: d.videoModel || VIDEO_MODELS[0] });
      update({ progress: next.progress || 0, progressMessage: next.message || `轮询中 ${i + 1}/120` });
      if (next.status === 'failed' || next.error) throw new Error(next.error || next.message || 'Grok OAuth 视频生成失败');
      if (next.videoUrl || (next.videoUrls && next.videoUrls.length > 0) || next.status === 'completed' || next.status === 'succeeded') return next;
    }
    throw new Error('Grok OAuth 视频生成超时，请稍后到异步任务中查看。');
  }, [d.duration, d.ratio, d.videoModel, d.videoResolution, payloadBase, update]);

  const handleRun = useCallback(async () => {
    if (isBusy) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setStreamingReply('');
    update({ status: mode === 'chat' ? 'streaming' : 'running', error: '', progressMessage: '', requestId: '' });
    try {
      const base = payloadBase();
      if (mode !== 'stt' && !base.prompt) {
        throw new Error('请填写 Prompt，或连接上游文本节点。');
      }

      if (mode === 'chat') {
        let reply = '';
        const messages = [{ role: 'user', content: base.prompt }];
        reply = await streamGrokOAuthChat(
          {
            ...base,
            model: d.chatModel || CHAT_MODELS[0],
            messages,
          },
          {
            signal: controller.signal,
            onDelta: (delta) => {
              setStreamingReply((prev) => prev + delta);
            },
          },
        );
        update({ status: 'success', reply, outputText: reply, text: reply, prompt: localPrompt, promptResolved: base.prompt, error: '' });
      } else if (mode === 'image') {
        const result = await generateGrokOAuthImage({
          ...base,
          model: d.imageModel || IMAGE_MODELS[0],
          ratio: d.ratio || '1:1',
          aspectRatio: d.ratio || '1:1',
          resolution: d.imageResolution || '1k',
        });
        const urls = asStringArray(result.imageUrls || result.imageUrl);
        update({ status: 'success', imageUrl: urls[0] || '', imageUrls: urls, promptResolved: base.prompt, error: '' });
      } else if (mode === 'video') {
        update({ status: 'submitting', progressMessage: '正在提交 Grok 视频任务...' });
        const result = await handleVideoSubmit(controller);
        const urls = asStringArray(result.videoUrls || result.videoUrl);
        update({ status: 'success', videoUrl: urls[0] || '', videoUrls: urls, promptResolved: base.prompt, progressMessage: '视频已生成', error: '' });
      } else if (mode === 'tts') {
        const result = await generateGrokOAuthTts({
          ...base,
          model: d.ttsModel || 'xai-tts',
          voiceId: d.voiceId || 'eve',
          language: d.language || 'zh',
          outputFormat: d.outputFormat || 'mp3',
        });
        const urls = asStringArray(result.audioUrls || result.audioUrl);
        update({ status: 'success', audioUrl: urls[0] || '', audioUrls: urls, promptResolved: base.prompt, error: '' });
      } else if (mode === 'stt') {
        const audioUrl = orderedAudios[0]?.url || d.audioUrl || '';
        if (!audioUrl) throw new Error('STT 需要连接上游音频，或节点已有音频输出。');
        const result = await transcribeGrokOAuthAudio({
          ...base,
          audioUrl,
          audios: [audioUrl],
          model: d.sttModel || 'xai-stt',
          language: d.language || 'zh',
        });
        const textOut = String(result.text || result.reply || result.prompt || '').trim();
        update({ status: 'success', reply: textOut, outputText: textOut, text: textOut, promptResolved: base.prompt, error: '' });
      }
      taskCompletionSound.notifyComplete(id, 'grok-oauth-agent');
      logBus.success('Grok OAuth Agent 运行完成', `grok:${id}`);
    } catch (e: any) {
      if (e?.name === 'AbortError') {
        update({ status: 'idle', error: '已中止 Grok OAuth 任务。' });
      } else {
        const message = e?.message || String(e);
        update({ status: 'error', error: message });
        logBus.error(message, `grok:${id}`);
      }
    } finally {
      abortRef.current = null;
    }
  }, [d.audioUrl, d.chatModel, d.imageModel, d.imageResolution, d.language, d.outputFormat, d.ratio, d.sttModel, d.ttsModel, d.voiceId, handleVideoSubmit, id, isBusy, localPrompt, mode, orderedAudios, payloadBase, update]);

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  useRunTrigger(id, handleRun, 'grok-oauth-agent');

  const renderModeParams = () => {
    if (mode === 'chat') {
      return (
        <label className="space-y-1">
          <span className="text-[10px]" style={{ color: subText }}>Chat 模型</span>
          <select className="nodrag nowheel w-full rounded px-2 py-1 text-[11px] outline-none" style={{ background: surface, color: text, border: `1px solid ${border}` }} value={d.chatModel || CHAT_MODELS[0]} onChange={(e) => update({ chatModel: e.target.value })}>
            {CHAT_MODELS.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
      );
    }
    if (mode === 'image') {
      return (
        <div className="grid grid-cols-3 gap-2">
          <SelectField label="图像模型" value={d.imageModel || IMAGE_MODELS[0]} options={IMAGE_MODELS} onChange={(value) => update({ imageModel: value })} surface={surface} text={text} border={border} subText={subText} />
          <SelectField label="比例" value={d.ratio || '1:1'} options={RATIOS} onChange={(value) => update({ ratio: value })} surface={surface} text={text} border={border} subText={subText} />
          <SelectField label="分辨率" value={d.imageResolution || '1k'} options={['1k', '2k']} onChange={(value) => update({ imageResolution: value })} surface={surface} text={text} border={border} subText={subText} />
        </div>
      );
    }
    if (mode === 'video') {
      return (
        <div className="grid grid-cols-2 gap-2">
          <SelectField label="视频模型" value={d.videoModel || VIDEO_MODELS[0]} options={VIDEO_MODELS} onChange={(value) => update({ videoModel: value })} surface={surface} text={text} border={border} subText={subText} />
          <SelectField label="比例" value={d.ratio || '16:9'} options={RATIOS} onChange={(value) => update({ ratio: value })} surface={surface} text={text} border={border} subText={subText} />
          <SelectField label="清晰度" value={d.videoResolution || '720p'} options={RESOLUTIONS.slice(0, 2)} onChange={(value) => update({ videoResolution: value })} surface={surface} text={text} border={border} subText={subText} />
          <NumberField label="时长(s)" value={Number(d.duration || 8)} min={1} max={15} onChange={(value) => update({ duration: value })} surface={surface} text={text} border={border} subText={subText} />
        </div>
      );
    }
    if (mode === 'tts') {
      return (
        <div className="grid grid-cols-3 gap-2">
          <TextField label="声音" value={d.voiceId || 'eve'} onChange={(value) => update({ voiceId: value })} surface={surface} text={text} border={border} subText={subText} />
          <TextField label="语言" value={d.language || 'zh'} onChange={(value) => update({ language: value })} surface={surface} text={text} border={border} subText={subText} />
          <SelectField label="格式" value={d.outputFormat || 'mp3'} options={['mp3', 'wav', 'opus']} onChange={(value) => update({ outputFormat: value })} surface={surface} text={text} border={border} subText={subText} />
        </div>
      );
    }
    return (
      <div className="rounded px-2 py-2 text-[11px]" style={{ background: surface, color: subText, border: `1px solid ${border}` }}>
        STT 会读取第一个上游音频，转写结果写入文本输出。
      </div>
    );
  };

  return (
    <div className="relative flex flex-col" style={rootStyle}>
      <Handle type="target" position={Position.Left} className="!border-0" style={{ ...handleStyle, background: PORT_COLOR.any, left: -6, top: '50%' }} />
      <Handle id="text" type="source" position={Position.Right} className="!border-0" style={{ ...handleStyle, background: PORT_COLOR.text, right: -6, top: '34%' }} />
      <Handle id="image" type="source" position={Position.Right} className="!border-0" style={{ ...handleStyle, background: PORT_COLOR.image, right: -6, top: '44%' }} />
      <Handle id="video" type="source" position={Position.Right} className="!border-0" style={{ ...handleStyle, background: PORT_COLOR.video, right: -6, top: '54%' }} />
      <Handle id="audio" type="source" position={Position.Right} className="!border-0" style={{ ...handleStyle, background: PORT_COLOR.audio, right: -6, top: '64%' }} />

      <div className="flex items-center gap-2 px-3 py-2" style={{ borderBottom: `1px solid ${border}` }}>
        <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0" style={{ background: surfaceStrong, color: accent, border: `1px solid ${border}` }}>
          <Bot size={18} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-bold text-sm">Grok OAuth Agent</div>
          <div className="text-[10px] truncate" style={{ color: subText }}>
            {status?.loggedIn ? `已登录 ${status.user || status.account || ''}` : (status?.message || GROK_OAUTH_PRIVATE_DISABLED_MESSAGE)}
          </div>
        </div>
        <button type="button" className="nodrag rounded px-2 py-1 text-[10px]" style={{ background: surface, color: text, border: `1px solid ${border}` }} onClick={() => void refreshStatus()} title="刷新状态">
          {statusLoading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
        </button>
      </div>

      <div className="nodrag nowheel max-h-[720px] overflow-y-auto p-3 space-y-3" onMouseDown={(e) => e.stopPropagation()}>
        <div className="grid grid-cols-2 gap-2">
          <button type="button" onClick={handleLogin} className="rounded px-2 py-1.5 text-[11px] font-bold flex items-center justify-center gap-1" style={{ background: status?.loggedIn ? surface : accent, color: status?.loggedIn ? text : (isPixel ? 'var(--px-surface)' : '#031712'), border: `1px solid ${border}` }}>
            {loginPolling ? <Loader2 size={12} className="animate-spin" /> : <LogIn size={12} />} 登录 / 绑定
          </button>
          <button type="button" onClick={handleLogout} className="rounded px-2 py-1.5 text-[11px] font-bold flex items-center justify-center gap-1" style={{ background: surface, color: text, border: `1px solid ${border}` }}>
            <LogOut size={12} /> 退出
          </button>
        </div>

        <div className="grid grid-cols-5 gap-1.5">
          {MODES.map((item) => {
            const Icon = item.icon;
            const active = mode === item.id;
            return (
              <button key={item.id} type="button" onClick={() => update({ mode: item.id, error: '', status: 'idle' })} className="rounded px-1 py-1.5 text-[10px] font-bold flex flex-col items-center gap-1" style={{ background: active ? accent : surface, color: active ? (isPixel ? 'var(--px-surface)' : '#031712') : text, border: `1px solid ${active ? accent : border}` }}>
                <Icon size={13} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>

        <MaterialPreviewSection
          texts={orderedTexts}
          images={orderedImages}
          videos={orderedVideos}
          audios={orderedAudios}
          order={materialOrder}
          onReorder={setMaterialOrder}
          isDark={isDark}
          isPixel={isPixel}
          title="上游素材 · Grok 输入"
        />

        <div>
          <label className="text-[10px] block mb-1" style={{ color: subText }}>Prompt / 指令</label>
          <MentionPromptInput
            title="Grok OAuth Prompt"
            value={localPrompt}
            mentions={promptMentions}
            materials={mentionMaterials}
            onChange={(value, mentions) => update({ prompt: value, promptMentions: mentions })}
            placeholder="写入指令，也可以 @ 引用上游图片、视频、音频"
            isDark={isDark}
            isPixel={isPixel}
            promptTemplateKind={mode === 'video' ? 'video' : mode === 'image' ? 'image' : false}
            className="w-full min-h-[86px] rounded px-2 py-2 text-[12px] outline-none"
            style={{ background: surface, color: text, border: `1px solid ${border}` }}
          />
        </div>

        <div className="space-y-2 rounded p-2" style={{ background: surface, border: `1px solid ${border}` }}>
          <div className="flex items-center gap-1 text-[11px] font-bold" style={{ color: text }}>
            <Wand2 size={12} /> 模式参数
          </div>
          {renderModeParams()}
        </div>

        {isBusy ? (
          <button type="button" onClick={handleStop} className="w-full rounded py-2 text-xs font-bold flex items-center justify-center gap-1.5" style={{ background: surface, color: text, border: `1px solid ${border}` }}>
            <Square size={13} /> 停止
          </button>
        ) : (
          <button type="button" onClick={() => void handleRun()} className="w-full rounded py-2 text-xs font-bold flex items-center justify-center gap-1.5" style={{ background: accent, color: isPixel ? 'var(--px-surface)' : '#031712', border: `1px solid ${accent}` }}>
            <Send size={13} /> 运行 Grok OAuth
          </button>
        )}

        {(isBusy || d.progressMessage) && (
          <div className="flex items-center gap-1 text-[10px]" style={{ color: accent }}>
            {isBusy && <Loader2 size={11} className="animate-spin" />}
            <span className="flex-1">{d.progressMessage || (mode === 'chat' ? '流式输出中...' : '运行中...')}</span>
            {d.requestId && <span style={{ color: subText }}>{String(d.requestId).slice(0, 10)}...</span>}
          </div>
        )}

        {error && (
          <div className="rounded px-2 py-2 text-[11px] flex items-start gap-1" style={{ color: danger, background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.35)' }}>
            <AlertCircle size={12} className="mt-0.5 shrink-0" />
            <span className="break-words">{error}</span>
          </div>
        )}

        {(streamingReply || outputText || imageUrls.length > 0 || videoUrls.length > 0 || audioUrls.length > 0) && (
          <div className="space-y-2 pt-2" style={{ borderTop: `1px solid ${border}` }}>
            {(streamingReply || outputText) && (
              <div className="rounded p-2 text-[11px] whitespace-pre-wrap max-h-40 overflow-y-auto" style={{ background: surface, color: text, border: `1px solid ${border}` }}>
                {streamingReply || outputText}
              </div>
            )}
            {imageUrls.map((url, index) => <SmartImage key={`${url}-${index}`} src={url} alt="Grok OAuth 图像输出" className="w-full rounded object-contain" thumbSize={720} />)}
            {videoUrls.map((url, index) => <video key={`${url}-${index}`} src={url} controls className="w-full rounded" />)}
            {audioUrls.map((url, index) => <audio key={`${url}-${index}`} src={url} controls className="w-full h-8" />)}
          </div>
        )}
      </div>
    </div>
  );
};

interface SelectFieldProps {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
  surface: string;
  text: string;
  border: string;
  subText: string;
}

function SelectField({ label, value, options, onChange, surface, text, border, subText }: SelectFieldProps) {
  return (
    <label className="space-y-1 min-w-0">
      <span className="text-[10px]" style={{ color: subText }}>{label}</span>
      <select className="nodrag nowheel w-full rounded px-2 py-1 text-[11px] outline-none truncate" style={{ background: surface, color: text, border: `1px solid ${border}` }} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((item) => <option key={item} value={item}>{item}</option>)}
      </select>
    </label>
  );
}

interface TextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  surface: string;
  text: string;
  border: string;
  subText: string;
}

function TextField({ label, value, onChange, surface, text, border, subText }: TextFieldProps) {
  return (
    <label className="space-y-1 min-w-0">
      <span className="text-[10px]" style={{ color: subText }}>{label}</span>
      <input className="nodrag nowheel w-full rounded px-2 py-1 text-[11px] outline-none" style={{ background: surface, color: text, border: `1px solid ${border}` }} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

interface NumberFieldProps extends Omit<TextFieldProps, 'value' | 'onChange'> {
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}

function NumberField({ label, value, min, max, onChange, surface, text, border, subText }: NumberFieldProps) {
  return (
    <label className="space-y-1 min-w-0">
      <span className="text-[10px]" style={{ color: subText }}>{label}</span>
      <input
        type="number"
        min={min}
        max={max}
        className="nodrag nowheel w-full rounded px-2 py-1 text-[11px] outline-none"
        style={{ background: surface, color: text, border: `1px solid ${border}` }}
        value={Number.isFinite(value) ? value : min}
        onChange={(e) => {
          const next = Number(e.target.value);
          if (Number.isFinite(next)) onChange(Math.max(min, Math.min(max, next)));
        }}
      />
    </label>
  );
}

export default memo(GrokOAuthAgentNode);

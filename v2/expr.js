// expr.js — ブレンドシェイプ(52) → 表情スコア(0..1) 変換ロジック
// MediaPipe FaceLandmarker の faceBlendshapes(ARKit互換52種)を入力にとる。
// 「採点」ではなく各表情の成立度を 0..1 で返し、しきい値＋時間キープで判定する。
//
// 対応表情: happy / surprised / puff / wink / neutral / angry / sad
//   ベロ出し(tongue)はブレンドシェイプに存在しない → VLMで別判定(needsVLM)。
//
// Node からもブラウザからも使えるよう UMD 風に export。

function exprScores(bs) {
  // bs: {categoryName: score} のマップ
  const g = (k) => bs[k] || 0;
  const avg = (a, b) => (g(a) + g(b)) / 2;

  const smile   = avg('mouthSmileLeft', 'mouthSmileRight');
  const jawOpen = g('jawOpen');
  const eyeWide = avg('eyeWideLeft', 'eyeWideRight');
  const browUp  = (g('browInnerUp') + avg('browOuterUpLeft', 'browOuterUpRight')) / 2;
  const browDn  = avg('browDownLeft', 'browDownRight');
  const frown   = avg('mouthFrownLeft', 'mouthFrownRight');
  const sneer   = avg('noseSneerLeft', 'noseSneerRight');
  const cheek   = g('cheekPuff');
  const press   = avg('mouthPressLeft', 'mouthPressRight');
  const blinkL  = g('eyeBlinkLeft');
  const blinkR  = g('eyeBlinkRight');
  const blinkMax = Math.max(blinkL, blinkR);
  const blinkMin = Math.min(blinkL, blinkR);

  // 「いかにも何かしている度」= neutral判定の裏返し
  const activity = Math.max(
    smile, jawOpen, cheek, browDn, frown, sneer, eyeWide, blinkMax,
    g('mouthPucker'), g('mouthFunnel'), avg('mouthUpperUpLeft', 'mouthUpperUpRight')
  );

  return {
    happy:     clamp(smile),
    // びっくり: 口が開く＋眉/目が上がる。jawOpen を必須要素に。
    surprised: clamp(Math.min(1, jawOpen * 0.6 + Math.max(eyeWide, browUp) * 0.6)) * gate(jawOpen, 0.25),
    puff:      clamp(cheek),
    // ウィンク: 片目だけ閉じる(左右差が大きい)。両目つむり(blinkMin高)は除外。
    wink:      clamp(blinkMax * (1 - blinkMin) * sym(blinkL, blinkR)),
    neutral:   clamp(1 - activity * 1.15),
    // おこる: 眉が下がる＋(口を結ぶ or 鼻にしわ)
    angry:     clamp(browDn * 0.7 + Math.max(press, sneer) * 0.5) * gate(browDn, 0.2),
    // かなしい: 口角が下がる＋眉の内側が上がる
    sad:       clamp(frown * 0.8 + g('browInnerUp') * 0.3) * gate(frown, 0.15),
  };
}

function clamp(v) { return Math.max(0, Math.min(1, v)); }
// x が th 未満ならほぼ0に落とす(必須条件ゲート)
function gate(x, th) { return x >= th ? 1 : x / th; }
// 左右差が大きいほど1に近づく(ウィンクの非対称性)
function sym(a, b) { const d = Math.abs(a - b); return clamp(d / 0.4); }

// 表情ごとの成立しきい値(公平で安定: 緩め。再現性重視)
const EXPR_THRESHOLD = {
  happy: 0.45, surprised: 0.45, puff: 0.40, wink: 0.45,
  neutral: 0.70, angry: 0.40, sad: 0.35,
};
const NEEDS_VLM = new Set(['tongue']);  // ブレンドシェイプで取れない表情

if (typeof module !== 'undefined') module.exports = { exprScores, EXPR_THRESHOLD, NEEDS_VLM };

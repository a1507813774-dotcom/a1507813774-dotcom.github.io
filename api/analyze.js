import { generateText } from 'ai';

function cors(req, res) {
  const origin = req.headers.origin || '';
  const allowed = ['https://a1507813774-dotcom.github.io'];
  if (origin && (allowed.includes(origin) || origin.endsWith('.vercel.app'))) {
    res.setHeader('Access-Control-Allow-Origin', origin);
  }
  res.setHeader('Vary', 'Origin');
  res.setHeader('Access-Control-Allow-Methods', 'POST,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type,X-Analyze-Token');
}

export default async function handler(req, res) {
  cors(req, res);

  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const requiredToken = process.env.ANALYZE_TOKEN;
  if (requiredToken) {
    const supplied = req.headers['x-analyze-token'];
    if (!supplied || supplied !== requiredToken) {
      return res.status(401).json({ error: 'Invalid analysis access code' });
    }
  }

  try {
    const { image, prompt } = req.body || {};
    if (typeof image !== 'string' || !image.startsWith('data:image/')) {
      return res.status(400).json({ error: 'A base64 image data URL is required' });
    }
    if (image.length > 7_000_000) {
      return res.status(413).json({ error: 'Image is too large' });
    }

    const match = image.match(/^data:(image\/[a-zA-Z0-9.+-]+);base64,(.+)$/s);
    if (!match) {
      return res.status(400).json({ error: 'Invalid base64 image data URL' });
    }

    const mediaType = match[1];
    const imageBytes = Buffer.from(match[2], 'base64');
    const instruction = typeof prompt === 'string' && prompt.trim()
      ? prompt.trim()
      : '请简洁描述这张图片中最重要、最值得注意的信息。';

    const model = process.env.AI_VISION_MODEL || 'openai/gpt-4.1-mini';

    const result = await generateText({
      model,
      messages: [
        {
          role: 'user',
          content: [
            { type: 'text', text: instruction },
            { type: 'image', image: imageBytes, mediaType }
          ]
        }
      ],
      maxOutputTokens: 600
    });

    return res.status(200).json({
      text: result.text || '',
      model
    });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ error: err?.message || 'AI analysis failed' });
  }
}

# Optional analysis prompt

This is **not** part of the default skill. `bili-transcript` only fetches and converts; the caller decides how to analyze the transcript.

If you want a structured summary after fetching, you can pass the transcript path to an LLM with a prompt like this:

```text
Read the transcript at <transcript_txt>. It comes from a Bilibili video.

Write a Chinese analysis with:
1. A one-sentence summary.
2. 3–7 core points, ordered by importance.
3. A timeline table with [mm:ss] timestamps.
4. Key arguments and memorable quotes, preserving timestamps.
5. Limitations, disagreements, and your own judgment.
6. 3–5 actionable takeaways.

Rules:
- Do not invent content that is not in the transcript.
- Mark inferences explicitly.
- If the transcript source starts with "asr:", warn about possible homophone errors.
- If partial=true, state the coverage at the top.
- Separate the video author's claims from your own evaluation.
```

For technical videos, add a glossary and correct obvious subtitle/ASR errors using context. For content-creation analysis, add hook, pacing, emotion curve, persuasion structure, and target audience.

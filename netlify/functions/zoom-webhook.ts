import type { Config, Context } from "@netlify/functions";
import { createHmac, timingSafeEqual } from "node:crypto";

declare const Netlify: {
  env: {
    get(name: string): string | undefined;
  };
};

type ZoomEvent = {
  event?: string;
  payload?: {
    plainToken?: string;
    object?: {
      id?: string | number;
      uuid?: string;
      meeting_id?: string | number;
      recording_files?: Array<{ id?: string; recording_type?: string; file_type?: string }>;
    };
    recording_file?: {
      id?: string;
      recording_type?: string;
      file_type?: string;
    };
  };
};

function env(name: string, fallback?: string): string {
  const value = Netlify.env.get(name) || fallback;
  if (!value) {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value;
}

function hmacHex(secret: string, value: string): string {
  return createHmac("sha256", secret).update(value).digest("hex");
}

function safeEqual(a: string, b: string): boolean {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  return left.length === right.length && timingSafeEqual(left, right);
}

function verifyZoomSignature(req: Request, rawBody: string, secret: string): boolean {
  const signature = req.headers.get("x-zm-signature") || "";
  const timestamp = req.headers.get("x-zm-request-timestamp") || "";
  if (!signature || !timestamp) {
    return false;
  }

  const nowSeconds = Math.floor(Date.now() / 1000);
  const requestSeconds = Number(timestamp);
  if (!Number.isFinite(requestSeconds) || Math.abs(nowSeconds - requestSeconds) > 300) {
    return false;
  }

  const expected = `v0=${hmacHex(secret, `v0:${timestamp}:${rawBody}`)}`;
  return safeEqual(signature, expected);
}

function transcriptFileId(event: ZoomEvent): string | undefined {
  const direct = event.payload?.recording_file;
  if (direct?.id) {
    return direct.id;
  }
  const files = event.payload?.object?.recording_files || [];
  const transcript = files.find((file) => {
    const recordingType = (file.recording_type || "").toLowerCase();
    const fileType = (file.file_type || "").toUpperCase();
    return recordingType === "audio_transcript" || recordingType === "transcript" || fileType === "VTT";
  });
  return transcript?.id;
}

function meetingId(event: ZoomEvent): string | undefined {
  const object = event.payload?.object;
  const value = object?.uuid || object?.id || object?.meeting_id;
  return value === undefined ? undefined : String(value);
}

async function dispatchWorkflow(event: ZoomEvent, rawBody: string): Promise<void> {
  const owner = env("GITHUB_OWNER");
  const repo = env("GITHUB_REPO");
  const token = env("GITHUB_DISPATCH_TOKEN");
  const workflow = env("GITHUB_MEETING_SUMMARY_WORKFLOW_ID", "meeting_summary_pipeline.yml");
  const ref = env("GITHUB_REF", "main");

  const resp = await fetch(`https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflow}/dispatches`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Accept": "application/vnd.github+json",
      "Content-Type": "application/json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({
      ref,
      inputs: {
        zoom_event_payload: rawBody,
        meeting_id: meetingId(event) || "",
        recording_file_id: transcriptFileId(event) || "",
      },
    }),
  });

  if (!resp.ok) {
    throw new Error(`GitHub workflow dispatch failed: ${resp.status} ${await resp.text()}`);
  }
}

export default async (req: Request, _context: Context) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  const secret = env("ZOOM_WEBHOOK_SECRET_TOKEN");
  const rawBody = await req.text();
  let event: ZoomEvent;
  try {
    event = JSON.parse(rawBody);
  } catch {
    return new Response("Invalid JSON", { status: 400 });
  }

  if (event.event === "endpoint.url_validation") {
    const plainToken = event.payload?.plainToken;
    if (!plainToken) {
      return new Response("Missing plainToken", { status: 400 });
    }
    return Response.json({
      plainToken,
      encryptedToken: hmacHex(secret, plainToken),
    });
  }

  if (!verifyZoomSignature(req, rawBody, secret)) {
    return new Response("Invalid Zoom signature", { status: 401 });
  }

  const allowedEvents = new Set(["recording.transcript_completed", "recording.completed"]);
  if (!event.event || !allowedEvents.has(event.event)) {
    return Response.json({ status: "ignored", event: event.event || "unknown" });
  }

  await dispatchWorkflow(event, rawBody);
  return Response.json({ status: "accepted" }, { status: 202 });
};

export const config: Config = {
  path: "/api/zoom/webhook",
  method: ["POST"],
};

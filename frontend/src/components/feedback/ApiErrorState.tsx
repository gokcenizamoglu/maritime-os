import { describeApiError, type ApiResult } from "@/lib/api/result";

type FailedApiResult = Exclude<ApiResult<unknown>, { ok: true }>;

/**
 * Renders the correct message for each `ApiResult` failure kind —
 * config/network/unauthenticated/forbidden/csrf/http/parse — rather
 * than one generic "error" bucket, per
 * docs/FRONTEND_INFORMATION_ARCHITECTURE.md's requirement to
 * distinguish these states, not collapse them.
 */
export function ApiErrorState({ result }: { result: FailedApiResult }) {
  const { title, description } = describeResult(result);
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-6">
      <p className="text-sm font-medium text-red-800">{title}</p>
      <p className="mt-1 text-sm text-red-700">{description}</p>
    </div>
  );
}

function describeResult(result: FailedApiResult): { title: string; description: string } {
  switch (result.kind) {
    case "config_error":
      return { title: "Configuration error", description: result.message };
    case "network_error":
      return {
        title: "Could not reach the backend",
        description: result.message,
      };
    case "unauthenticated":
      return {
        title: "Not signed in",
        description: describeApiError(result.error) ?? "Please sign in to continue.",
      };
    case "forbidden":
      return {
        title: "Access denied",
        description:
          describeApiError(result.error) ?? "Your session may have expired — try signing in again.",
      };
    case "csrf_failure":
      return {
        title: "Session expired",
        description: "Your session token is out of date. Please sign in again.",
      };
    case "http_error":
      return {
        title: `Request failed (${result.status})`,
        description: describeApiError(result.error) ?? "An unexpected error occurred.",
      };
    case "parse_error":
      return {
        title: `Unexpected response (${result.status})`,
        description: "The backend returned a response that wasn't valid JSON.",
      };
  }
}

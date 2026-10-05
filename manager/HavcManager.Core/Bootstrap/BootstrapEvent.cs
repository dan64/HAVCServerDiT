using System.Text.Json;
using System.Text.Json.Serialization;

namespace HavcManager.Core.Bootstrap;

/// <summary>
/// One event line emitted by the bootstrap in --json-progress mode
/// (protocol: PHASE0_SPEC §5, emitted by havc/progress.py).
/// Known kinds: plan, step_begin, step_ok, step_skip, step_error, log, result.
///
/// Note: the `steps` field carries different shapes depending on the event —
/// an array of step objects for `plan`, a step count (number) for `result`;
/// use <see cref="PlanSteps"/> and <see cref="StepCount"/> to read it.
/// </summary>
public sealed record BootstrapEvent
{
    [JsonPropertyName("event")] public string Kind { get; init; } = "";
    [JsonPropertyName("ts")] public double Timestamp { get; init; }
    [JsonPropertyName("id")] public string? StepId { get; init; }
    [JsonPropertyName("title")] public string? StepTitle { get; init; }
    [JsonPropertyName("detail")] public string? Detail { get; init; }
    [JsonPropertyName("reason")] public string? Reason { get; init; }
    [JsonPropertyName("error")] public string? Error { get; init; }
    [JsonPropertyName("remediation")] public string? Remediation { get; init; }
    [JsonPropertyName("message")] public string? Message { get; init; }
    [JsonPropertyName("ok")] public bool? Ok { get; init; }
    [JsonPropertyName("steps")] public JsonElement? Steps { get; init; }

    /// <summary>Steps of a `plan` event; null for every other kind.</summary>
    public IReadOnlyList<PlanStep>? PlanSteps
    {
        get
        {
            if (Steps is not { } element || element.ValueKind != JsonValueKind.Array)
                return null;
            return element.Deserialize<List<PlanStep>>();
        }
    }

    /// <summary>Step count of a `result` event; null for every other kind.</summary>
    public int? StepCount
    {
        get
        {
            if (Steps is not { } element || element.ValueKind != JsonValueKind.Number)
                return null;
            return element.GetInt32();
        }
    }
}

/// <summary>One entry of the plan event (id, title and optional skip reason).</summary>
public sealed record PlanStep
{
    [JsonPropertyName("id")] public string Id { get; init; } = "";
    [JsonPropertyName("title")] public string Title { get; init; } = "";
    [JsonPropertyName("skip_reason")] public string? SkipReason { get; init; }
}

using System.Text.Json;
using HavcManager.Core.Bootstrap;

namespace HavcManager.Core.Tests;

public class BootstrapEventTests
{
    [Fact]
    public void Parses_a_step_error_line()
    {
        var e = JsonSerializer.Deserialize<BootstrapEvent>(
            """{"event": "step_error", "ts": 1.5, "id": "wheel", "error": "boom", "remediation": "fix it"}""")!;
        Assert.Equal("step_error", e.Kind);
        Assert.Equal(1.5, e.Timestamp);
        Assert.Equal("wheel", e.StepId);
        Assert.Equal("boom", e.Error);
        Assert.Equal("fix it", e.Remediation);
    }

    [Fact]
    public void Parses_a_plan_line_with_steps()
    {
        const string json = """
        {"event": "plan", "ts": 1, "steps": [
             {"id": "runtime", "title": "Python runtime", "hint": "x", "skip_reason": "already present"},
             {"id": "venv", "title": "Virtual environment", "hint": "y", "skip_reason": null}]}
        """;
        var e = JsonSerializer.Deserialize<BootstrapEvent>(json)!;
        Assert.Equal("plan", e.Kind);
        Assert.Equal(2, e.PlanSteps!.Count);
        Assert.Equal("runtime", e.PlanSteps[0].Id);
        Assert.Equal("already present", e.PlanSteps[0].SkipReason);
        Assert.Null(e.PlanSteps[1].SkipReason);
        Assert.Null(e.StepCount);
    }

    [Fact]
    public void Parses_a_result_line()
    {
        var e = JsonSerializer.Deserialize<BootstrapEvent>(
            """{"event": "result", "ts": 2, "ok": false, "steps": 5, "skipped": 1}""")!;
        Assert.Equal("result", e.Kind);
        Assert.False(e.Ok);
        Assert.Equal(5, e.StepCount);
        Assert.Null(e.PlanSteps);
    }
}

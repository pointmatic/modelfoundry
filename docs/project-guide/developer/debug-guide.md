# Debug Guide for LLMs

This guide provides a structured approach for LLMs to help developers debug issues in existing software projects. It emphasizes test-driven debugging, root cause analysis, and preventing regressions.

**Context:** This guide assumes you're working in a project created using the workflow defined in `project_guide.md`, which means the following documentation structure exists:
- `docs/specs/features.md` - Feature requirements (what the project does)
- `docs/specs/tech_spec.md` - Technical specification (how it's built)
- `docs/specs/stories.md` - Implementation stories and changelog

---

## Core Debugging Principles

### 1. Test First, Fix Second

**Always write a failing test before attempting a fix.**

**Why:**
- A test provides a concrete, reproducible demonstration of the bug
- It gives you a clear "exit condition" (test passes = bug fixed)
- It prevents "oops...not fixed yet" cycles where you think you've fixed it but haven't
- It serves as regression protection for the future
- It forces you to understand the bug well enough to codify it

**Process:**
1. Read the bug report or error message
2. Write a minimal test case that demonstrates the failure
3. Run the test to confirm it fails
4. Implement the fix
5. Run the test to confirm it passes
6. Run the full test suite to ensure no regressions

**Example:**

❌ **What NOT to do:**
```
User: "The data processor is producing duplicate IDs"
LLM: "Let me fix the ID generation function..." [makes changes]
LLM: "Let me test with the real data file..." [processes file]
LLM: "Hmm, still not working, let me try a different approach..."
```

✅ **What TO do:**
```
User: "The data processor is producing duplicate IDs"
LLM: "Let me write a test that demonstrates this bug..."
[Writes test_id_generator_with_multiple_sources()]
LLM: "Test fails as expected. Now implementing fix..."
[Implements fix]
LLM: "Test passes. Running full suite to check for regressions..."
```

### 2. Understand Before Acting

**Analyze the root cause before proposing solutions.**

**Questions to ask:**
- What is the expected behavior?
- What is the actual behavior?
- Where in the codebase does this behavior originate?
- Why wasn't this caught by existing tests?
- Is this a requirements gap, implementation bug, or test coverage gap?

### 3. Prefer Unit Tests Over Integration Tests for Debugging

**Use the smallest possible test scope.**

**Why:**
- Unit tests are faster to run
- Unit tests are easier to debug (fewer moving parts)
- Unit tests pinpoint the exact function/module with the bug
- Integration tests are valuable but unstable for debugging

**Test Hierarchy:**
1. **Unit test** - Test a single function in isolation (preferred for debugging)
2. **Integration test** - Test multiple components together
3. **End-to-end test** - Test the full pipeline (useful for verification, not debugging)

**Example:**
- ❌ Testing ID generation by processing a full data file with thousands of records
- ✅ Testing ID generation with a minimal list of 8 test objects

---

## Structured Debugging Workflow

### Step 1: Reproduce the Bug

**Goal:** Create a minimal, reliable reproduction of the issue.

**Actions:**
1. Read the bug report carefully
2. Identify the symptoms (error message, incorrect output, unexpected behavior)
3. Determine the input that triggers the bug
4. Create a minimal test case that reproduces the bug

**Output:** A failing test that demonstrates the bug

### Step 2: Analyze Root Cause

**Goal:** Understand why the bug exists.

**Questions to investigate:**

#### A. Requirements Analysis
- Is the expected behavior clearly defined in `features.md`?
- Is the implementation approach specified in `tech_spec.md`?
- Is there ambiguity in the requirements?
- Was this requirement overlooked during initial design?

#### B. Implementation Analysis
- Which function/module contains the bug?
- What assumptions did the code make that are incorrect?
- Are there edge cases that weren't considered?
- Is the algorithm fundamentally flawed or just missing a check?

#### C. Test Coverage Analysis
- Why didn't existing tests catch this?
- Is there a gap in test coverage?
- Are the tests testing the wrong thing?
- Are the tests too high-level (integration) vs. unit tests?

**Output:** A clear understanding of:
1. What went wrong
2. Where it went wrong
3. Why it went wrong
4. Why tests didn't catch it

### Step 3: Design the Fix

**Goal:** Plan a minimal, targeted fix.

**Considerations:**
- What's the smallest change that fixes the root cause?
- Does this fix introduce new edge cases?
- Does this fix require changes to the public API?
- Will this fix break existing functionality?

**Approaches:**
1. **Fix the implementation** - Bug in the code logic
2. **Add validation** - Missing input validation or error checking
3. **Refactor** - Fundamental design flaw requiring restructuring
4. **Update requirements** - Behavior is actually correct, requirements were wrong

**Output:** A clear plan for the fix

### Step 4: Implement the Fix

**Goal:** Make the minimal change to fix the bug.

**Process:**
1. Implement the fix
2. Run the failing test - it should now pass
3. Run the full test suite - no regressions
4. Add additional tests for edge cases if needed

**Output:** Working code with passing tests

### Step 5: Document and Prevent

**Goal:** Ensure this class of bug doesn't happen again.

**Actions:**
1. Update `features.md` or `tech_spec.md` if requirements were ambiguous
2. Add test coverage for the bug scenario
3. Document the fix in `stories.md` (create a new story following the format in `project_guide.md`)
4. Consider if similar bugs exist elsewhere in the codebase

**Output:** Updated documentation and comprehensive test coverage

---

## Root Cause Analysis Framework

### Requirements Gap Analysis

**Check `features.md` for:**
- [ ] Is the expected behavior explicitly defined?
- [ ] Are edge cases documented?
- [ ] Are constraints clearly stated?
- [ ] Are validation rules specified?

**Check `tech_spec.md` for:**
- [ ] Is the implementation approach clear?
- [ ] Are data structures well-defined?
- [ ] Are algorithms specified?
- [ ] Are module responsibilities clear?

**Common requirements gaps:**
- Implicit assumptions not documented
- Edge cases not considered
- Ambiguous language ("should", "may", "usually")
- Missing validation rules
- Incomplete acceptance criteria

### Test Coverage Gap Analysis

**Questions:**
- [ ] Do unit tests exist for this function?
- [ ] Do tests cover edge cases?
- [ ] Do tests cover error conditions?
- [ ] Are tests testing implementation details or behavior?
- [ ] Are integration tests masking unit test gaps?

**Common test gaps:**
- High-level integration tests without unit tests
- Happy path testing only (no edge cases)
- Testing implementation details instead of behavior
- Missing negative test cases (error conditions)
- Insufficient boundary testing

### Implementation Bug Analysis

**Questions:**
- [ ] Is the algorithm correct?
- [ ] Are there off-by-one errors?
- [ ] Are there race conditions or ordering issues?
- [ ] Are assumptions about input data incorrect?
- [ ] Are there type mismatches or conversion errors?

**Common implementation bugs:**
- Incorrect loop bounds
- Wrong comparison operators
- Missing null/empty checks
- Incorrect data structure usage
- Side effects from shared state

---

## Case Study: Duplicate ID Generation Bug

### The Bug

**Context:** A data processing system generates unique IDs for records. The system has two data sources: initial state (loaded from a snapshot) and new transactions (from an event stream). Both sources feed into a combined output.

**Symptom:** Record IDs were duplicated when initial state and new transactions occurred on the same date (e.g., `REC-2023-01-01-0001` appeared 6 times instead of being split into separate records).

**Impact:** Violated uniqueness constraint, compromised data integrity, made output unusable for downstream systems.

### Root Cause Analysis

#### 1. Requirements Gap?

**Requirements stated:**
```
Generate unique record IDs:
- Format: REC-YYYY-MM-DD-NNNN
- YYYY-MM-DD: record date
- NNNN: sequential number starting at 0001 for each date
- All entries for a single record share the same ID
- IDs are numbered in the order they appear in the output
```

**Analysis:**
- ✅ Requirement states "unique record IDs"
- ✅ Requirement states "sequential number starting at 0001 for each date"
- ❌ **GAP:** Requirement doesn't specify what happens when initial state and transactions are combined
- ❌ **GAP:** Phrase "All entries for a single record share the same ID" is ambiguous when combining data sources
- ❌ **GAP:** No explicit requirement that each record must have a globally unique ID across all sources

**Verdict:** **Partial requirements gap** - The requirement was present but not explicit enough about the combination scenario.

#### 2. Test Coverage Gap?

**Existing tests:**
- ✅ Tests for `load_initial_state()` in isolation
- ✅ Tests for `process_transactions()` in isolation
- ❌ **GAP:** No tests for combining initial state and transactions on the same date
- ❌ **GAP:** No tests validating ID uniqueness across the full output
- ❌ **GAP:** Integration tests used real data but didn't assert on ID uniqueness

**Verdict:** **Critical test coverage gap** - The specific scenario (initial state + transactions on same date) was never tested.

#### 3. Implementation Bug?

**Code analysis:**
```python
# In processor.py
initial_records = load_initial_state(...)  # IDs start at 0001
new_records = process_transactions(...)     # IDs also start at 0001
all_records.extend(initial_records)
all_records.extend(new_records)
all_records.sort(key=lambda r: (r.date, r.id))  # Sort interleaves duplicates
```

**Analysis:**
- ❌ Both functions independently assign IDs starting at 0001
- ❌ No coordination between the two ID generation schemes
- ❌ Sort interleaves records with duplicate IDs, creating ID collisions

**Verdict:** **Implementation bug** - The code didn't account for combining records from two sources.

### Why Wasn't This Caught Earlier?

**Three contributing factors:**

1. **Requirements ambiguity** - The requirement for "unique IDs" existed but didn't explicitly address the combination scenario.

2. **Test coverage gap** - No unit test verified ID uniqueness when combining initial state and transactions. Integration tests existed but didn't assert on this property.

3. **Test-last approach** - The initial fix attempt was made without first writing a test, leading to a "not fixed yet" cycle. Only after writing `test_id_generation_with_multiple_sources()` was the bug properly fixed.

### Lessons Learned

1. **Write tests for integration points** - When combining outputs from two functions, test the combined result, not just each function in isolation.

2. **Test invariants explicitly** - "IDs must be unique" is an invariant that should be tested explicitly, not assumed.

3. **Test first, always** - Writing the test first would have:
   - Demonstrated the bug clearly
   - Provided a concrete exit condition
   - Prevented the "try fix, check manually, still broken" cycle

4. **Unit tests > Integration tests for debugging** - The end-to-end test with real data files was unstable and slow. The focused unit test with minimal test objects was stable and precise.

5. **Clarify requirements proactively** - When implementing features that combine multiple components, explicitly document how they interact.

---

## Common Debugging Scenarios

### Scenario 1: "It works in tests but fails in production"

**Root cause:** Test data doesn't match production data characteristics

**Debugging steps:**
1. Capture the production input that fails
2. Create a test case with that exact input
3. Verify the test fails
4. Fix the bug
5. Verify the test passes
6. Add similar test cases for related edge cases

### Scenario 2: "Tests pass but the feature doesn't work"

**Root cause:** Tests are testing the wrong thing or testing implementation details

**Debugging steps:**
1. Review what the tests actually assert
2. Verify tests are testing behavior, not implementation
3. Add tests that verify the actual user-facing behavior
4. Fix the implementation to match requirements
5. Ensure tests now verify the correct behavior

### Scenario 3: "Fixing one bug breaks something else"

**Root cause:** Insufficient test coverage or tight coupling

**Debugging steps:**
1. Identify what broke (which tests failed)
2. Understand why the fix caused the breakage
3. Determine if the original fix was correct
4. Either:
   - Adjust the fix to not break existing functionality
   - Update the broken tests if they were testing incorrect behavior
5. Add tests to prevent this regression

### Scenario 4: "Can't reproduce the bug"

**Root cause:** Missing context about the environment or input

**Debugging steps:**
1. Ask user for exact input data, command line, environment
2. Ask user for exact error message or incorrect output
3. Try to reproduce with minimal test case
4. If still can't reproduce, ask user to run with verbose logging
5. Use logging output to understand what's different

---

## Debugging Checklist

Before proposing a fix, verify:

- [ ] I have written a test that demonstrates the bug
- [ ] The test fails before the fix
- [ ] I understand the root cause (requirements, implementation, or test gap)
- [ ] I have designed a minimal fix
- [ ] The fix addresses the root cause, not just symptoms
- [ ] The test passes after the fix
- [ ] All existing tests still pass (no regressions)
- [ ] I have added additional tests for edge cases if needed
- [ ] I have documented the fix in `stories.md` (created a new story)
- [ ] I have updated `features.md` or `tech_spec.md` if requirements were ambiguous

---

## Anti-Patterns to Avoid

### ❌ Fix First, Test Later

**Problem:** You think you've fixed it, but you haven't. No concrete exit condition.

**Solution:** Always write the failing test first.

### ❌ Testing with Real Data Only

**Problem:** Real data is complex, slow, and hard to debug. "Wildly unstable."

**Solution:** Create minimal unit tests with synthetic data.

### ❌ Fixing Symptoms Instead of Root Cause

**Problem:** Bug will resurface in a different form.

**Solution:** Analyze why the bug exists, not just what the bug is.

### ❌ Skipping Root Cause Analysis

**Problem:** You don't learn from the bug, similar bugs will occur.

**Solution:** Always ask "why wasn't this caught earlier?"

### ❌ Over-Engineering the Fix

**Problem:** Introduces complexity, new bugs, or breaks existing functionality.

**Solution:** Make the minimal change that fixes the root cause.

### ❌ Not Updating Requirements

**Problem:** Ambiguous requirements lead to more bugs.

**Solution:** If requirements were unclear, update them as part of the fix.

---

## When to Escalate to User

**Escalate when:**
- Requirements are fundamentally ambiguous and you need user clarification
- Multiple valid interpretations exist for expected behavior
- Fix would require breaking changes to public API
- Fix would require significant refactoring
- You've tried multiple approaches and tests still fail

**Don't escalate when:**
- You haven't written a test yet
- You haven't analyzed the root cause
- You haven't tried the obvious fix
- You're just stuck on implementation details

---

## Summary

**The Golden Rule of Debugging:**

> **Write a failing test first. Fix the code second. Verify the test passes third.**

This simple rule prevents:
- "Oops, not fixed yet" cycles
- Regressions
- Unclear exit conditions
- Wasted time on manual testing

**The Three Questions:**

1. **Why did this bug exist?** (Requirements gap, implementation bug, or both?)
2. **Why didn't tests catch it?** (Test coverage gap, wrong test level, or testing wrong thing?)
3. **How do we prevent this class of bug?** (Update requirements, add tests, refactor?)

**The Test Hierarchy:**

1. **Unit tests** - Fast, focused, stable (use for debugging)
2. **Integration tests** - Medium scope, useful for verification
3. **End-to-end tests** - Slow, complex, unstable (use for final validation only)

Follow this guide to debug systematically, learn from bugs, and prevent regressions.

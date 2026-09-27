# Randomized Testing and Runtime Monitoring for Robotic Navigation Systems

## Project Overview

Robotic navigation systems operate in dynamic environments and are expected to satisfy multiple safety and behavioral requirements throughout their execution. Testing such systems manually or using a small collection of predefined scenarios may fail to expose unexpected combinations of environmental conditions and robot behaviors.

This project aims to develop a **randomized testing framework for robotic navigation systems in MuJoCo**, combined with **multi-property runtime monitoring**.

The framework automatically generates navigation test scenarios, executes them in the MuJoCo simulation environment, observes the robot state throughout each execution, and evaluates a collection of predefined specifications.

The main idea can be summarized as:

```text
Random Test Case
       │
       ▼
MuJoCo Simulation
       │
       ▼
x(0) → x(1) → x(2) → ... → x(T)
       │
       ▼
Multi-Property Runtime Monitor
       │
       ▼
Specification Verdict Vector
[T, T, F, T, ..., F]
```

Each generated test case therefore produces not only a simulation result, but also an ordered Boolean vector describing which specifications were satisfied or violated.

---

## Motivation

A robotic navigation system may need to satisfy many requirements simultaneously.

Examples include:

- The robot must not collide with obstacles.
- The robot must maintain a minimum distance from obstacles.
- After a certain point in the execution, the robot must not exceed a specified velocity.
- The robot must not remain stationary for too long unless it has reached its destination.
- The robot must reduce its velocity under specified dangerous conditions.
- The robot's angular or linear velocity must remain within defined limits.

Some requirements can be evaluated directly from the current robot state, while others depend on conditions or behavior over time.

For example:

> After 5 seconds, the robot must not travel faster than 10 m/s.

This can be represented conceptually as

```text
time >= 5 seconds  →  velocity <= 10 m/s
```

More complex requirements may depend on multiple previous states and therefore require temporal monitoring.

Testing all of these requirements across a sufficiently diverse collection of navigation scenarios creates two related problems:

1. **How can a large and diverse set of navigation test cases be generated automatically?**
2. **How can many behavioral and safety specifications be evaluated efficiently during those simulations?**

This project investigates these problems together.

---

## Randomized Test Case Generation

Instead of relying only on manually designed scenarios, the framework generates variations of the robot and its environment automatically.

A test case may contain parameters such as:

```text
Test Case
├── Robot initial position
├── Robot initial orientation
├── Goal position
├── Obstacle positions
├── Obstacle properties
├── Initial robot velocity
├── Environment parameters
├── Sensor conditions
└── Other simulation parameters
```

A generated test case is executed in MuJoCo.

By varying these parameters, the framework can explore a much larger input space than would normally be practical with manually constructed tests.

The objective is to discover scenarios that expose unusual, unsafe, or specification-violating robot behavior.

---

## MuJoCo Execution Traces

During a simulation, MuJoCo provides the state of the system at each simulation step.

The state at time `t` can be represented as a vector:

```text
x(t) = [
    position,
    orientation,
    linear_velocity,
    angular_velocity,
    joint_positions,
    joint_velocities,
    contact_information,
    sensor_values,
    ...
]
```

The simulation therefore produces an execution trace:

```text
x(0) → x(1) → x(2) → ... → x(T)
```

Specifications are evaluated against this stream of states.

This allows the framework to detect not only whether the robot eventually reaches its goal, but also **how the robot behaves during the execution**.

---

## Specification Monitoring

Let the system contain an ordered collection of specifications:

```text
Φ = [φ1, φ2, φ3, ..., φm]
```

At runtime, the monitoring system evaluates these specifications using the state information produced by MuJoCo.

For example:

```text
φ1 = robot does not collide
φ2 = robot maintains minimum obstacle clearance
φ3 = velocity remains below the allowed limit
φ4 = robot does not remain stuck for too long
φ5 = robot reacts correctly to dangerous proximity
...
```

The monitor produces an ordered Boolean verdict vector:

```text
V = [True, True, False, True, ..., False]
```

The position of each value corresponds to a fixed specification.

For example:

```text
Index    Specification                         Verdict
0        Collision safety                      True
1        Minimum obstacle clearance            True
2        Velocity constraint                    False
3        Stuck detection                        True
4        Dangerous-proximity response           False
```

This representation makes the outcome of a generated test case machine-readable.

Instead of simply classifying a simulation as "successful" or "failed," the framework records **which properties were satisfied and which were violated**.

---

## Temporal Specifications

Not every specification can be evaluated by inspecting a single MuJoCo state.

For example, a simple constraint such as

```text
velocity <= 10 m/s
```

can be evaluated directly.

However, a requirement such as

> The robot must not remain stationary for more than 3 seconds unless it has reached its destination.

requires information from multiple simulation steps.

Similarly, requirements may involve conditions such as:

```text
if condition A occurred,
property B must have held during a specified time interval
```

These requirements motivate the use of temporal logic and runtime verification.

The project investigates the use of **multi-property temporal monitoring**, inspired by the approach presented in *Multi-Property Temporal Logic Monitoring*, where multiple temporal properties are represented using a shared computation structure.

---

## Multi-Property Monitoring

A navigation system may contain many specifications with common subexpressions.

For example, several specifications may depend on:

```text
distance_to_obstacle < threshold
```

or:

```text
robot_velocity > threshold
```

Evaluating every specification independently may repeatedly calculate the same expressions.

Instead, shared subexpressions can be represented once in a **Directed Acyclic Graph (DAG)** and reused by multiple specifications.

Conceptually:

```text
                 Specification φ1
                       ▲
                       │
                 safe_distance
                  ▲          ▲
                  │          │
           Specification φ2  │
                             │
                      Specification φ3
```

The shared representation can reduce redundant computation when many properties are monitored simultaneously.

This becomes particularly relevant for randomized testing because the same specification set may need to be evaluated over thousands of independently generated simulation runs.

---

## Problems Addressed by the Project

The project focuses on several related problems.

### Limited Test Scenario Coverage

Manually constructed test cases cover only a small portion of the possible navigation scenarios.

Randomized generation allows the framework to explore different combinations of robot states, obstacle configurations, goals, environmental parameters, and other simulation conditions.

### Detecting Behavioral Failures

A robot reaching its destination does not necessarily mean that its execution was correct.

It may have:

- moved dangerously close to an obstacle,
- temporarily exceeded a velocity constraint,
- become stuck for an unacceptable amount of time,
- behaved incorrectly under a particular condition,
- or violated another requirement before eventually reaching the goal.

Runtime monitoring allows these intermediate behaviors to be detected.

### Monitoring Multiple Requirements

Realistic robotic systems have multiple requirements that must be checked simultaneously.

Evaluating them independently can introduce redundant computation, particularly when specifications contain common expressions.

Multi-property monitoring attempts to reduce this redundancy through shared computation.

### Representing Test Outcomes

A simple pass/fail result loses information about the behavior exposed by a test.

The Boolean specification vector

```text
[T, F, T, T, F, ...]
```

provides a richer description of each test case.

Two tests that both "fail" may therefore still represent very different behaviors:

```text
Test A → [T, F, T, T, T]

Test B → [T, T, T, F, T]
```

The first exposes a violation of `φ2`, while the second exposes a violation of `φ4`.

This representation can later be used to analyze test diversity, specification coverage, and potentially guide future test generation.

---

## Overall Goal

The overall objective of the project is to combine

```text
Randomized Test Generation
            +
Robotic Navigation Simulation
            +
Multi-Property Runtime Monitoring
```

into a single automated testing framework.

The intended workflow is:

```text
                ┌──────────────────────┐
                │ Random Test Generator │
                └──────────┬───────────┘
                           │
                           ▼
                    Test Scenario
                           │
                           ▼
                ┌──────────────────────┐
                │        MuJoCo        │
                └──────────┬───────────┘
                           │
                           ▼
              x(0), x(1), ..., x(T)
                           │
                           ▼
             ┌────────────────────────┐
             │ Multi-Property Monitor │
             └────────────┬───────────┘
                          │
                          ▼
                 [T, T, F, ..., T]
                          │
                          ▼
              Test Analysis / Storage
```

The project ultimately aims to investigate whether randomized simulation combined with efficient multi-property monitoring can provide a scalable method for discovering safety and behavioral violations in robotic navigation systems.

## Reference

The multi-property monitoring component is inspired by:

**A. Demir and D. Ulus, "Multi-Property Temporal Logic Monitoring," 2026.**

The paper proposes sharing common subformulas between temporal specifications using a DAG-based representation and a data-oriented execution model, reducing redundant computation when multiple properties are monitored over the same execution trace.

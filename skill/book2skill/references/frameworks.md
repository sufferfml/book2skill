# Framework representation and evidence review

Start with the problem the book addresses for the intended use. Reconstruct: premises → concepts and relationships → derivation/mechanism → conditional conclusions → counterexamples and boundaries → how to test and revise the framework in a new situation. For normative arguments, state value objectives and tradeoffs rather than presenting them as empirical laws.

`schema model` defines the JSON contract; `template model` creates an unfilled skeleton. Core fields:

- `claims`: statements, provenance types, source segments, conditions, and unknowns.
- `relations`: endpoint claim IDs, relationship types, explanations, and source support for the relationship itself. `illustrates` denotes an example; it does not automatically establish a mechanism.
- `frameworks`: the core problem, mechanism, claims/relationships, dependencies, applicability conditions, boundaries, observations, situational mapping, alternative explanations/actions, checks, revision rules, and unknowns.

`author_explicit` requires direct support. `author_reconstructed` retains evidence across passages and explains the reconstruction. `model_extension` denotes an additional hypothesis. New boundaries or mechanisms stated in framework fields must also correspond to claims with declared provenance; moving text into a framework field must not bypass provenance requirements.

The tool checks IDs, locations, coverage, relationship endpoints, dependency cycles, and references across structural units. It cannot determine whether citations provide semantic support or whether two structural units belong to different chapters in the actual publication. Reviewers must return to the source instead of optimizing for validator acceptance.

For each review target, check:

1. Does the source address the same subject, scale, time frame, and problem?
2. Does it support the relationship's direction, conditions, and strength, or does it merely mention the two concepts separately?
3. Do later passages introduce restrictions, counterexamples, terminology changes, or conflicts? Can the example support the proposed generalization?
4. Do the framework's mechanism or boundaries exceed the reviewed claims? If so, explicitly classify the addition as a model hypothesis or revise it.
5. Are the facts to observe and the conditions for revising a judgment on a new problem actionable? Do missing conditions remain visible?

In a review, `supported` means the reviewer considers the source supportive, not that the claim is valid in the real world. `hypothesis` is reserved for `model_extension`. `unsupported`, `uncertain`, or `unresolved` blocks packaging; revise and review again first. Do not assign `supported` merely to finish the workflow.

For batched reviews, the tool includes relationship endpoints, relevant frameworks, and source passages. Record unresolved issues spanning batches in `unresolved`. Completing later reviews does not automatically erase earlier issues; clear them through an overall revision.

Use development cases to expose representation defects rather than memorize answers: change surface details while preserving structure; preserve surface details while changing a decisive condition; remove a key fact; introduce evidence that conflicts with the initial judgment. For each case, record which judgment should change and which mechanism remains applicable. Subsequent held-out cases must not have participated in this revision.

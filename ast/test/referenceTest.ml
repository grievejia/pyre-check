(** Copyright (c) 2016-present, Facebook, Inc.

    This source code is licensed under the MIT license found in the
    LICENSE file in the root directory of this source tree. *)


open Core

open OUnit2
open Ast
open Pyre
open Test


let test_create _ =
  let assert_create ?prefix input =
    let expected =
      prefix >>| (fun prefix -> prefix ^ "." ^ input) |> Option.value ~default:input
    in
    let prefix = prefix >>| Reference.create in
    assert_equal expected (Reference.show (Reference.create ?prefix input))
  in
  assert_create "";
  assert_create "a";
  assert_create "a.b.c";
  assert_create ~prefix:"a.b" "c.d.e"


let test_expression _ =
  let assert_expression reference expression =
    let expected =
      Expression.Access expression
      |> Node.create_with_default_location
    in
    let actual =
      Reference.create reference
      |> Reference.expression
    in
    assert_equal
      ~printer:Expression.show
      expected
      actual
  in
  assert_expression "a" (SimpleAccess [Identifier "a"]);
  assert_expression "a.b.c" (SimpleAccess [Identifier "a"; Identifier "b"; Identifier "c"])


let test_new_expression _ =
  let node = Node.create_with_default_location in
  let assert_expression reference expression =
    let expected =
      Expression.Name expression
      |> node
    in
    let actual =
      Reference.create reference
      |> Reference.new_expression
    in
    assert_equal
      ~printer:Expression.show
      expected
      actual
  in
  assert_expression "a" (Expression.Name.Identifier "a");
  assert_expression
    "a.b"
    (Expression.Name.Attribute {
      base = Expression.Name (Expression.Name.Identifier "a") |> node;
      attribute = "b"
    });
  assert_expression
    "a.b.c"
    (Expression.Name.Attribute {
      base = Expression.Name (
        Expression.Name.Attribute {
          base = Expression.Name (Expression.Name.Identifier "a") |> node;
          attribute = "b";
        })
        |> node;
      attribute = "c"
    })


let test_prefix _ =
  let check_prefix prefix reference =
    Reference.is_prefix ~prefix:(Reference.create prefix) (Reference.create reference)
  in
  assert_true (check_prefix "" "a");
  assert_true (check_prefix "a" "a.b");
  assert_true (check_prefix "a.b" "a.b");
  assert_false (check_prefix "a.c" "c.a");

  let check_suffix suffix reference =
    Reference.is_suffix ~suffix:(Reference.create suffix) (Reference.create reference)
  in
  assert_true (check_suffix "" "a");
  assert_true (check_suffix "a" "a");
  assert_true (check_suffix "b.c" "a.b.c");
  assert_false (check_suffix "a" "a.b");

  let check_strict prefix reference =
    Reference.is_strict_prefix ~prefix:(Reference.create prefix) (Reference.create reference)
  in
  assert_true (check_strict "a" "a.b");
  assert_true (check_strict "a.b" "a.b.c");
  assert_false (check_strict "a.b" "a.b");
  assert_false (check_strict "a.b.c" "a.b");
  assert_false (check_strict "a" "b.a");

  let assert_drop_prefix prefix reference dropped =
    let prefix = Reference.create prefix in
    let reference = Reference.create reference in
    let dropped = Reference.create dropped in
    assert_equal ~printer:Reference.show dropped (Reference.drop_prefix ~prefix reference)
  in
  assert_drop_prefix "a" "a.b" "b";
  assert_drop_prefix "a" "b.a" "b.a";
  assert_drop_prefix "a.b" "a.b.c" "c";
  assert_drop_prefix "a" "a" "a";

  let assert_prefix reference prefix =
    assert_equal
      ~printer:(fun reference -> reference >>| Reference.show |> Option.value ~default:"None")
      (prefix >>| Reference.create)
      (Reference.prefix (Reference.create reference))
  in
  assert_prefix "a" None;
  assert_prefix "a.b" (Some "a");
  assert_prefix "a.b.c" (Some "a.b");

  let assert_last reference last =
    assert_equal
      ~printer:Reference.show
      (Reference.create last)
      (Reference.last (Reference.create reference))
  in
  assert_last "a" "a";
  assert_last "a.b" "b"


let () =
  "reference">:::[
    "create">::test_create;
    "expression">::test_expression;
    "new_expression">::test_new_expression;
    "prefix">::test_prefix;
  ]
  |> Test.run

// vim: set ts=2 sw=2 et :
//
// Compile-fail fixture for spec 12 compile-fail parity. Contains a deliberate
// SystemVerilog syntax error so that both `rtl_buddy test compile_fail` and
// `rtl-comrade test compile_fail` fail at compile and report FAIL with a
// non-zero exit. Paired with the `compile_fail` test in tests.yaml.
module tb_compile_fail;

  logic clk;

  initial begin
    // Deliberate syntax error: assignment with no right-hand side.
    clk = ;
  end

endmodule

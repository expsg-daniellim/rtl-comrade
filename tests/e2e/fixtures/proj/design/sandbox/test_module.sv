// vim: set ts=2 sw=2 et :
//
// Expedera R&D Pte Ltd Confidential 2024
//


interface test_mem_if#(parameter WIDTH);

  logic [WIDTH-1:0] a;
  logic [WIDTH-1:0] b;

  modport mgr (output a, b);
  modport sub (input a, b);

endinterface


module test_mem_if_assign ( test_mem_if.sub in, test_mem_if.mgr out );
  assign out.a = in.a;
  assign out.b = in.b;
endmodule

//module test_mem_if_assign2 ( test_mem_if.sub in, test_mem_if.mgr out );
//  assign out.a = in.a;
//  assign out.b = in.b;
//endmodule

module test_module
  #(parameter WIDTH=4) 
  (
    input clk,
    input rst,
    input [WIDTH-1:0] a, 
    input [WIDTH-1:0] b, 
    output logic[WIDTH-1:0] z
  );

  always_ff @(posedge clk) begin
    if (rst) begin
      z <= '0;
    end else begin
      z <= a + b;
    end
  end

endmodule

module test_module_2 #(
  )
  ( 
    input clk,
    input rst,
    test_mem_if.sub m,
    output logic z
  );

  always_ff @(posedge clk) begin
    if (rst) begin
      z <= '0;
    end else begin
      z <= m.a + m.b;
    end
  end

endmodule

module test_module_3 #(parameter WIDTH=4) ( input clk, input rst, test_mem_if.sub m, output [WIDTH-1:0] z);

genvar i;

generate
  for (i=0; i<2; i++) begin:gen_i

    // note: verilator has trouble finding an interface defined in a generate block
    test_mem_if #( .WIDTH( m.WIDTH ) ) i_m ();
    logic i_z;
    test_module_2 i_m2 ( .clk, .rst, .m(i_m), .z(i_z) );

    //this works, .out can find i_m
    test_mem_if_assign i_assign( .in( m ), .out( i_m ) );
  end:gen_i
endgenerate


  //this doesn't work, verilator can't find .out(gen_i[0].i_m)
  //test_mem_if_assign i_assign( .in( m ), .out( gen_i[0].i_m ) );
  //%Error: ../src/test_module.sv:16:49: Parent instance's interface is not found: 'test_mem_if'
  //                                   : ... note: In instance 'tb_top.i_dut_2.i_assign'
  //                                      16 | module test_mem_if_assign ( test_mem_if.mgr in, test_mem_if.sub out );
  //                                            |                                                 ^~~~~~~~~~~

//this doesn't work, same issue as above
//generate
//  for (genvar j=0; j<2; j++) begin:gen_j
//    test_mem_if_assign i_assign( .in( m ), .out( gen_i[0].i_m ) );
//  end:gen_j
//endgenerate

  //this works
  //local interface is ok (without generate block), verilator can find i_mx connected to .out
  //test_mem_if #(.WIDTH( m.WIDTH )) i_mx();
  //test_mem_if_assign i_assign( .in( m ), .out( i_mx ) );

  //this works 
  //we confirm that verilator has correct path to the generated interface signals
  //assign gen_i[0].i_m.a = m.a;
  //assign gen_i[0].i_m.b = m.b;
  //assign gen_i[1].i_m.a = m.a;
  //assign gen_i[1].i_m.b = m.b;

logic[1:0] z_bus;
generate
  for (i=0; i<2; i++) begin:gen_i2
    assign z_bus[i] = gen_i[i].i_z;
  end:gen_i2
endgenerate

  assign z = |z_bus;

endmodule



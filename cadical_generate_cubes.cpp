#include "cadical.hpp"

#include <climits>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <string>

namespace {

int parse_nonnegative(const char *text, const char *name) {
  char *end = nullptr;
  const long value = std::strtol(text, &end, 10);
  if (!text[0] || *end || value < 0 || value > 30) {
    std::cerr << "invalid " << name << ": " << text << '\n';
    std::exit(2);
  }
  return static_cast<int>(value);
}

int parse_positive(const char *text, const char *name) {
  char *end = nullptr;
  const long value = std::strtol(text, &end, 10);
  if (!text[0] || *end || value <= 0 || value > INT_MAX) {
    std::cerr << "invalid " << name << ": " << text << '\n';
    std::exit(2);
  }
  return static_cast<int>(value);
}

} // namespace

int main(int argc, char **argv) {
  if (argc < 4 || argc > 8) {
    std::cerr << "usage: cadical_generate_cubes INPUT DEPTH OUTPUT "
                 "[MIN_DEPTH] [MAX_VARIABLE | VARIABLE_BASE VARIABLE_STRIDE "
                 "[VARIABLE_LIMIT]]\n";
    return 2;
  }

  const char *input = argv[1];
  const int depth = parse_nonnegative(argv[2], "depth");
  const char *output = argv[3];
  const int min_depth =
      argc >= 5 ? parse_nonnegative(argv[4], "minimum depth") : 0;
  const int max_variable =
      argc == 6 ? parse_positive(argv[5], "maximum variable") : 0;
  const int variable_base =
      argc >= 7 ? parse_positive(argv[5], "variable base") : 0;
  const int variable_stride =
      argc >= 7 ? parse_positive(argv[6], "variable stride") : 0;
  const int variable_limit =
      argc == 8 ? parse_positive(argv[7], "variable limit") : 0;
  if (min_depth > depth) {
    std::cerr << "minimum depth exceeds depth\n";
    return 2;
  }

  CaDiCaL::Solver solver;
  solver.set("quiet", 1);
  int variables = 0;
  if (const char *error = solver.read_dimacs(input, variables)) {
    std::cerr << error << '\n';
    return 1;
  }
  if (max_variable > variables) {
    std::cerr << "maximum variable exceeds DIMACS variable count\n";
    return 2;
  }
  if (variable_base > variables) {
    std::cerr << "variable base exceeds DIMACS variable count\n";
    return 2;
  }
  if (variable_limit > variables || (variable_limit &&
                                     variable_limit < variable_base)) {
    std::cerr << "invalid variable limit\n";
    return 2;
  }
  if (max_variable) {
    const std::string value = std::to_string(max_variable);
    if (setenv("CADICAL_CUBE_MAX_INTERNAL_VAR", value.c_str(), 1)) {
      std::perror("setenv");
      return 1;
    }
    for (int variable = 1; variable <= max_variable; ++variable)
      solver.freeze(variable);
  } else if (variable_base) {
    const std::string base = std::to_string(variable_base);
    const std::string stride = std::to_string(variable_stride);
    const std::string limit = std::to_string(variable_limit);
    if (setenv("CADICAL_CUBE_INTERNAL_BASE", base.c_str(), 1) ||
        setenv("CADICAL_CUBE_INTERNAL_STRIDE", stride.c_str(), 1) ||
        (variable_limit &&
         setenv("CADICAL_CUBE_MAX_INTERNAL_VAR", limit.c_str(), 1))) {
      std::perror("setenv");
      return 1;
    }
    const int last_variable = variable_limit ? variable_limit : variables;
    for (int variable = variable_base; variable <= last_variable;
         variable += variable_stride)
      solver.freeze(variable);
  }

  const CaDiCaL::Solver::CubesWithStatus result =
      solver.generate_cubes(depth, min_depth);
  std::ofstream stream(output);
  if (!stream) {
    std::cerr << "cannot open output: " << output << '\n';
    return 1;
  }

  stream << "{\n"
         << "  \"schema\": \"erdos176.cadical-cubes.v1\",\n"
         << "  \"status\": " << result.status << ",\n"
         << "  \"nvars\": " << variables << ",\n"
         << "  \"depth\": " << depth << ",\n"
         << "  \"min_depth\": " << min_depth << ",\n"
         << "  \"max_variable\": " << max_variable << ",\n"
         << "  \"variable_base\": " << variable_base << ",\n"
         << "  \"variable_stride\": " << variable_stride << ",\n"
         << "  \"variable_limit\": " << variable_limit << ",\n"
         << "  \"cubes\": [";
  for (std::size_t index = 0; index < result.cubes.size(); ++index) {
    if (index)
      stream << ',';
    stream << "\n    [";
    const std::vector<int> &cube = result.cubes[index];
    for (std::size_t position = 0; position < cube.size(); ++position) {
      if (position)
        stream << ", ";
      stream << cube[position];
    }
    stream << ']';
  }
  if (!result.cubes.empty())
    stream << '\n';
  stream << "  ]\n}\n";
  if (!stream) {
    std::cerr << "failed while writing output\n";
    return 1;
  }
  return 0;
}

{
  description = "AI Receptionist — reproducible dev environment";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in {
      devShells.${system}.default = pkgs.mkShell {
        packages = with pkgs; [
          python312
          nodejs_20
          docker
          docker-compose
          gnumake
          pre-commit
          postgresql_16
        ];
        shellHook = ''
          echo "AI Receptionist dev shell"
          echo "  make bootstrap  — install deps"
          echo "  make up         — start Docker stack"
        '';
      };
    };
}

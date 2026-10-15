import unittest
from pc_lab.blitz import (Score,gravity,level_lines,ground_locks,ground_action,air_route,
                         settle,t_spin,score_move,BLITZ_OPTIONS)
from pc_lab.engine import empty_board,load_kicks,lock,cells,reachable_locks
from pc_lab.solver import ROOT

class BlitzTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.kicks=load_kicks(ROOT/'data/srsplus90.properties')

    def test_official_replay_level_curve(self):
        self.assertEqual([level_lines(i) for i in (1,10,11,15)],[3,21,24,32])
        self.assertAlmostEqual(gravity(10),2.01423,places=4)
        self.assertGreater(gravity(14),20)
        self.assertEqual(BLITZ_OPTIONS['objective_time'],120000)

    def test_score_pc_b2b_combo_and_nonclear_chain(self):
        first=Score(level=10).place(4,pc=True)
        self.assertEqual(first.score,43000)
        idle=first.place(0)
        self.assertEqual(idle.b2b,1)
        second=idle.place(2,'full')
        self.assertEqual(second.score-first.score,18000)
        third=second.place(4)
        self.assertEqual(third.score-second.score,12500)
        single=third.place(1)
        self.assertEqual(single.b2b,0)

    def test_level_advances_using_carry_including_native_level_16(self):
        score=Score().place(4,pc=True)
        self.assertEqual((score.level,score.level_progress),(2,1))
        score=Score(level=14,level_progress=29).place(2)
        self.assertEqual((score.level,score.level_progress),(15,1))
        score=score.place(4)
        self.assertEqual(score.level,15)
        # User's native Blitz: 266 lines gives Level 16 and 6 carried lines.
        score=Score().place(0)
        for _ in range(133):score=score.place(2)
        self.assertEqual((score.level,score.level_progress),(16,6))
        self.assertEqual(level_lines(16),34)
        self.assertGreater(gravity(16),gravity(15))
        fixed=Score(level=15,level_cap=15)
        for _ in range(20):fixed=fixed.place(2)
        self.assertEqual((fixed.level,fixed.level_progress),(15,40))

    def test_ground_routes_settle_after_every_input(self):
        board=list(empty_board());board[0]='____XX____';board[1]='____XX____';board=tuple(board)
        for piece in 'IJLOSTZ':
            routes=ground_locks(board,piece,self.kicks,allow180=True)
            self.assertTrue(routes)
            for points,route in routes.items():
                pose=settle(board,piece,(4,21,0))
                for action in route['actions'][:-1]:pose=ground_action(board,piece,pose,action,self.kicks)
                self.assertEqual(tuple(sorted(cells(piece,pose[2],pose[0],pose[1]))),points)
                lock(board,points,piece)

    def test_ground_sfinder_validator_agrees_with_route_geometry(self):
        board=empty_board()
        for piece in 'IJLOSTZ':
            simple=reachable_locks(board,piece,self.kicks,'ground')
            rich=ground_locks(board,piece,self.kicks)
            self.assertEqual(set(simple),set(rich))

    def test_i_180_has_srs_half_cell_anchor_correction(self):
        board=empty_board();pose=(4,4,0)
        result=ground_action(board,'I',pose,'cw180',self.kicks)
        self.assertEqual({x for x,y in cells('I',result[2],result[0],result[1])},{3,4,5,6})

    def test_wall_routes_use_arr_zero_and_fewer_inputs(self):
        for piece in 'IJLOSTZ':
            routes=ground_locks(empty_board(),piece,self.kicks,allow180=True,allow_wall=True)
            for points,route in routes.items():
                pose=settle(empty_board(),piece,(4,21,0))
                for action in route['actions'][:-1]:pose=ground_action(empty_board(),piece,pose,action,self.kicks)
                self.assertEqual(tuple(sorted(cells(piece,pose[2],pose[0],pose[1]))),points)
        target=tuple(sorted(cells('O',0,0,0)))
        route=ground_locks(empty_board(),'O',self.kicks,wanted=target,allow_wall=True)[target]
        self.assertEqual(route['actions'],['left_wall','hard_drop'])

    def test_native_sonic_wall_settles_between_horizontal_steps(self):
        board=('_SSIIIIJJJ','_TSSSS_J__','___OO____L')+empty_board()[3:]
        self.assertEqual(ground_action(board,'Z',(5,4,3),'right_wall',self.kicks),(7,2,3))

    def test_air_wall_crosses_a_cavity_that_traps_a_grounded_o(self):
        board=('XX__XX____','XX__XX____')+empty_board()[2:]
        target=tuple(sorted(cells('O',0,0,2)))
        self.assertEqual(ground_locks(board,'O',self.kicks,wanted=target,allow_wall=True),{})
        route=air_route(board,'O',self.kicks,(4,21,0),target)
        self.assertEqual(route['actions'],['left_wall','hard_drop'])

    def test_air_kicks_choose_two_quarter_turns_over_move_and_half_turn(self):
        from pc_lab.finesse import input_cost,estimated_faults
        board=('X___XX____','XX_X_XXX__','______XX__','____XXX__X')+empty_board()[4:]
        start=(4,4,0);target=((2,5),(3,5),(4,4),(4,5))
        route=air_route(board,'J',self.kicks,start,target,max_inputs=2)
        self.assertEqual(route['actions'],['cw','cw','hard_drop'])
        self.assertEqual(input_cost(route['actions']),2)
        self.assertEqual(estimated_faults('J',target,route['actions']),0)
        pose=start
        from pc_lab.blitz import raw_ground_action
        for action in route['actions'][:-1]:pose=raw_ground_action(board,'J',pose,action,self.kicks)
        landing=settle(board,'J',pose)
        self.assertEqual(tuple(sorted(cells('J',landing[2],landing[0],landing[1]))),target)
        self.assertIsNone(air_route(board,'J',self.kicks,start,target,max_inputs=1))

    def test_three_corners_and_facing_not_non_t_immobility(self):
        board=list(empty_board());board[0]='___X_X____';board[2]='___X_X____';board=tuple(board)
        self.assertEqual(t_spin(board,'T',(4,1,2),'cw'),'full')
        self.assertEqual(t_spin(board,'T',(4,1,2),'left'),'none')
        self.assertEqual(t_spin(board,'L',(4,1,2),'cw'),'none')
        board=list(board);board[0]='_____X____';board=tuple(board)
        self.assertEqual(t_spin(board,'T',(4,1,2),'cw'),'mini')
        self.assertEqual(t_spin(board,'T',(4,1,2),'cw',True),'full')

    def test_scoring_search_can_take_visible_hold_for_quad_pc(self):
        board=list(empty_board())
        for y in range(4):board[y]='XXXXXXXXX_'
        board=tuple(board)
        step=score_move(board,'O','TLZSJ','I',self.kicks,Score(level=10),
                        allow180=True,budget=.03)
        self.assertEqual(step['piece'],'I')
        self.assertTrue(step['hold_used'])
        self.assertEqual(len(step['cleared_rows']),4)
        self.assertEqual(step['board_after'],empty_board())

    def test_empty_hold_consumes_two_actual_queue_members(self):
        board=list(empty_board())
        for y in range(4):board[y]='XXXXXXXXX_'
        step=score_move(tuple(board),'O','ITLZS',None,self.kicks,Score(),budget=.01)
        self.assertEqual(step['piece'],'I')
        self.assertEqual(step['queue_index_after'],2)
        self.assertEqual(step['hold_after'],'O')

    def test_go_overlay_does_not_hide_the_first_grounded_piece(self):
        import json
        from PIL import Image
        from pc_lab.vision import read_state,Geometry
        directory=ROOT/'output/live-20261014-174654-0b48d253'
        if not directory.exists():self.skipTest('native regression fixture unavailable')
        geometry=Geometry(**json.loads((directory/'initial-observation.json').read_text())['geometry'])
        image=Image.open(directory/'initial-09.png')
        state=read_state(image,geometry,expected_board=empty_board(),ignore_countdown=True)
        self.assertEqual(state['active'],'O')
        self.assertEqual(state['board'],empty_board())
        self.assertEqual(len(state['active_cells']),4)

    def test_java_search_prunes_the_same_ground_landings_as_python(self):
        import os,subprocess,tempfile
        from pathlib import Path
        from pc_lab.solver import java_path,SFINDER
        board=list(empty_board());board[0]='XX___XXXX_';board[1]='XX___X____';board=tuple(board)
        with tempfile.TemporaryDirectory(dir=ROOT/'output') as directory:
            field=Path(directory)/'field.txt'
            for layout in (empty_board(),board):
                field.write_text('6\n'+'\n'.join(reversed(layout[:6]))+'\n')
                for mode,piece in ((m,p) for m in ('ground','ground180') for p in 'IJLOSTZ'):
                    output=subprocess.run([str(java_path()),'-cp',os.pathsep.join((str(ROOT/'tools/bridge'),str(SFINDER))),
                        'PcSearch','--'+mode+'-landings',str(field),piece,str(ROOT/'data/srsplus90.properties')],
                        capture_output=True,text=True,check=True).stdout
                    actual={tuple(sorted(cells(piece,r,x,y))) for x,y,r in
                            [tuple(map(int,line.split(','))) for line in output.splitlines()]}
                    expected={p for p in ground_locks(layout,piece,self.kicks,allow180=mode=='ground180') if max(y for x,y in p)<6}
                    self.assertEqual(actual,expected,(mode,piece,layout[:2]))

    def test_unreachable_target_never_returns_another_placement(self):
        impossible=((0,19),(0,20),(0,21),(0,22))
        self.assertEqual(ground_locks(empty_board(),'I',self.kicks,wanted=impossible),{})

    def test_rotation_then_falling_into_corners_is_not_native_t_spin(self):
        # The downloaded CUSTOM replay counts this as a normal Double.
        board=('LL_SSSSZZI','LL__SSSSZI','LL_______I')+empty_board()[3:]
        target=((2,0),(2,1),(2,2),(3,1))
        route=ground_locks(board,'T',self.kicks,wanted=target)
        self.assertEqual(route[target]['spin'],'none')
        self.assertEqual(ground_locks(board,'T',self.kicks,wanted=target,wanted_spin='mini'),{})

    def test_ground_search_budget_keeps_warm_worker_and_next_request_clean(self):
        import tempfile
        from pathlib import Path
        from pc_lab.search_worker import search,close_worker,_local
        with tempfile.TemporaryDirectory(dir=ROOT/'output') as directory:
            field=Path(directory)/'field.txt'
            field.write_text('2\n__XXXXXXXX\n__XXXXXXXX\n')
            args=[str(field),'O','2','ground180','avoid',str(ROOT/'data/srsplus90.properties')]
            try:
                output,code=search(args,2,lambda:False)
                self.assertEqual(code,0);self.assertIn('SOLUTION ',output)
                pid=_local.worker.process.pid
                # A one-millisecond cooperative budget expires while loading
                # candidates, without discarding the already warm JVM.
                field.write_text('4\n__________\n__________\n__________\n__________\n')
                timed=[str(field),'JLOSTZIJLO','4','ground180','use',str(ROOT/'data/srsplus90.properties')]
                output,code=search(timed,.001,lambda:False)
                self.assertEqual(code,0);self.assertIn('SEARCH_BUDGET',output)
                self.assertEqual(_local.worker.process.pid,pid)
                field.write_text('2\n__XXXXXXXX\n__XXXXXXXX\n')
                output,code=search(args,1,lambda:False)
                self.assertEqual(code,0);self.assertIn('SOLUTION ',output)
                self.assertEqual(_local.worker.process.pid,pid)
            finally:close_worker()

if __name__=='__main__':unittest.main()

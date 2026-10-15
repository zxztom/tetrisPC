import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.regex.*;
import common.datastore.action.Action;
import common.datastore.action.MinimalAction;
import core.action.candidate.Candidate;
import core.field.Field;
import core.field.FieldFactory;
import core.mino.Mino;
import core.mino.MinoFactory;
import core.mino.Piece;
import core.srs.Rotate;

/** 20G / held-sonic-drop candidates for sfinder's normal PC checker.
 * Every shift/rotation is followed by falling to the floor. This prunes
 * unreachable placements DURING search, not after the first air solution.
 * Python independently reconstructs the resulting operations and Hold.
 */
public final class GroundCandidate implements Candidate<Action> {
    private final Mino[][] minos=new Mino[7][4];
    private final Map<String,int[][]> kicks=new HashMap<>();
    private final Properties raw=new Properties();
    private final boolean allow180;
    private final boolean finesseOnly;
    private final Map<Integer,Map<Long,Integer>> ideals=new HashMap<>();
    private long deadline=Long.MAX_VALUE;
    public static final class BudgetExceeded extends RuntimeException {
        private static final long serialVersionUID=1L;
    }
    public void setDeadline(long deadline) {this.deadline=deadline;}
    private void checkBudget() {if(System.nanoTime()>=deadline)throw new BudgetExceeded();}
    private static final int[][][] TURN180={
      {{0,0},{0,1},{1,1},{-1,1},{1,0},{-1,0}},
      {{0,0},{1,0},{1,2},{1,1},{0,2},{0,1}},
      {{0,0},{0,-1},{-1,-1},{1,-1},{-1,0},{1,0}},
      {{0,0},{-1,0},{-1,2},{-1,1},{0,2},{0,1}}};
    private static final int[][][] I180={{{1,-1},{1,0}},{{-1,-1},{0,-1}},{{-1,1},{-1,0}},{{1,1},{0,1}}};
    private record Key(long board,int piece,int height) {}
    private record Pose(int x,int y,int r,int depth) {}
    private final Map<Key,Set<Action>> cache=new LinkedHashMap<>() {
        protected boolean removeEldestEntry(Map.Entry<Key,Set<Action>> entry) {return size()>8000;}
    };

    public GroundCandidate(MinoFactory factory,Path kickFile) throws Exception {
        this(factory,kickFile,false);
    }
    public GroundCandidate(MinoFactory factory,Path kickFile,boolean allow180) throws Exception {
        this(factory,kickFile,allow180,false);
    }
    public GroundCandidate(MinoFactory factory,Path kickFile,boolean allow180,boolean finesseOnly) throws Exception {
        this.allow180=allow180;
        this.finesseOnly=finesseOnly;
        for (Piece p:Piece.values()) for (Rotate r:Rotate.values()) minos[p.ordinal()][r.getNumber()]=factory.create(p,r);
        try (java.io.Reader reader=Files.newBufferedReader(kickFile)) {raw.load(reader);}
        for (String key:raw.stringPropertyNames()) kicks.put(key,resolve(key));
    }
    private int[][] resolve(String key) {
        String value=raw.getProperty(key).trim();
        if (value.startsWith("&")) return resolve(value.substring(1));
        Matcher m=Pattern.compile("\\(\\s*@?\\s*([+-]?\\d+)\\s*,\\s*@?\\s*([+-]?\\d+)\\s*\\)").matcher(value);
        List<int[]> result=new ArrayList<>();
        while(m.find()) result.add(new int[]{Integer.parseInt(m.group(1)),Integer.parseInt(m.group(2))});
        return result.toArray(new int[0][]);
    }
    private boolean fits(Field field,Mino mino,int x,int y,int height) {
        for (int[] p:mino.getPositions()) {
            int nx=x+p[0],ny=y+p[1];
            if (nx<0 || nx>=10 || ny<0 || ny>=24 || (ny<height&&!field.isEmpty(nx,ny))) return false;
        }
        return true;
    }
    private Pose settle(Field field,Mino[] shapes,Pose p,int height) {
        int y=p.y;
        while(fits(field,shapes[p.r],p.x,y-1,height)) y--;
        return new Pose(p.x,y,p.r,p.depth);
    }
    private long footprint(Mino shape,int x,int y,boolean normalize) {
        int floor=normalize?y+shape.getMinY():0;long bits=0;
        for(int[] c:shape.getPositions())bits|=1L<<((y+c[1]-floor)*10+x+c[0]);
        return bits;
    }
    private List<Pose> next(Field field,Piece piece,Pose p,int height,boolean grounded) {
        Mino[] shapes=minos[piece.ordinal()];Mino shape=shapes[p.r];List<Pose> out=new ArrayList<>();
        for(int dx:new int[]{-1,1}) {
            if(fits(field,shape,p.x+dx,p.y,height)) {
                Pose moved=new Pose(p.x+dx,p.y,p.r,p.depth+1);
                out.add(grounded?settle(field,shapes,moved,height):moved);
            }
            if(grounded&&!finesseOnly)continue;
            Pose wall=p;
            for(int i=0;i<10&&fits(field,shape,wall.x+dx,wall.y,height);i++) {
                Pose moved=new Pose(wall.x+dx,wall.y,p.r,p.depth+1);
                wall=grounded?settle(field,shapes,moved,height):moved;
            }
            if(wall.x!=p.x||wall.y!=p.y)out.add(wall);
        }
        for(int turn:(grounded&&allow180&&piece!=Piece.O?new int[]{1,-1,2}:new int[]{1,-1})) {
            int nr=(p.r+turn+4)%4;
            int[][] offsets=turn==2?(piece==Piece.I?I180[p.r]:TURN180[p.r]):kicks.get(piece+"."+"NESW".charAt(p.r)+"NESW".charAt(nr));
            for(int[] offset:offsets) {
                int nx=p.x+offset[0],ny=p.y+offset[1];
                if(fits(field,shapes[nr],nx,ny,height)) {
                    Pose moved=new Pose(nx,ny,nr,p.depth+(turn==2&&finesseOnly?2:1));
                    out.add(grounded?settle(field,shapes,moved,height):moved);break;
                }
            }
        }
        return out;
    }
    private Map<Long,Integer> ideal(Piece piece) {
        Map<Long,Integer> hit=ideals.get(piece.ordinal());if(hit!=null)return hit;
        Field empty=FieldFactory.createField("__________".repeat(6));
        PriorityQueue<Pose> todo=new PriorityQueue<>(Comparator.comparingInt(Pose::depth));
        todo.add(new Pose(4,21,0,0));Set<String> seen=new HashSet<>();Map<Long,Integer> out=new HashMap<>();
        while(!todo.isEmpty()) {
            Pose p=todo.remove();if(!seen.add(p.x+","+p.y+","+p.r))continue;
            out.merge(footprint(minos[piece.ordinal()][p.r],p.x,p.y,true),p.depth,Math::min);
            if(p.depth<5)todo.addAll(next(empty,piece,p,6,false));
        }
        ideals.put(piece.ordinal(),out);return out;
    }
    public Set<Action> search(Field field,Piece piece,int height) {
        checkBudget();
        Key key=new Key(field.getBoard(0),piece.ordinal(),height);
        Set<Action> hit=cache.get(key);if(hit!=null) return hit;
        Mino[] shapes=minos[piece.ordinal()];
        Pose spawn=new Pose(4,21,0,0);
        if(!fits(field,shapes[0],4,21,height)) return Collections.emptySet();
        Queue<Pose> todo=finesseOnly?new PriorityQueue<>(Comparator.comparingInt(Pose::depth)):new ArrayDeque<>();todo.add(settle(field,shapes,spawn,height));
        boolean[] seen=new boolean[10*24*4];
        Set<Action> actions=new LinkedHashSet<>();Map<Long,Integer> footprints=new HashMap<>();
        Map<Action,Integer> ranks=new LinkedHashMap<>();Map<Long,Integer> ideal=finesseOnly?ideal(piece):Collections.emptyMap();
        while(!todo.isEmpty()) {
            checkBudget();
            Pose p=todo.remove();int id=(p.y*10+p.x)*4+p.r;
            if(seen[id])continue;seen[id]=true;
            Mino shape=shapes[p.r];
            if(p.y+shape.getMaxY()<height) {
                long footprint=footprint(shape,p.x,p.y,false);
                int faults=finesseOnly?Math.max(0,p.depth-ideal.getOrDefault(footprint(shape,p.x,p.y,true),0)):0;
                int rank=finesseOnly?faults*100+p.depth:0;
                if((!finesseOnly||faults==0)&&rank<footprints.getOrDefault(footprint,Integer.MAX_VALUE)) {
                    Action a=MinimalAction.create(p.x,p.y,Rotate.getRotate(p.r));
                    // Equivalent orientations share a physical target.
                    ranks.entrySet().removeIf(e->footprint(shapes[e.getKey().getRotate().getNumber()],e.getKey().getX(),e.getKey().getY(),false)==footprint);
                    ranks.put(a,rank);footprints.put(footprint,rank);
                }
            }
            if(p.depth>=(finesseOnly?4:12))continue;
            todo.addAll(next(field,piece,p,height,true));
        }
        ranks.entrySet().stream().sorted(Map.Entry.comparingByValue()).forEach(e->actions.add(e.getKey()));
        cache.put(key,actions);return actions;
    }
}
